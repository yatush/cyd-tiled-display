import asyncio
import requests
import threading
from aioesphomeapi import APIClient

class HAProxy:
    def __init__(self, session_id, port, ha_url, ha_token, supervisor_token, check_session_callback):
        self.session_id = session_id
        self.port = port
        self.ha_url = ha_url
        self.ha_token = ha_token
        self.supervisor_token = supervisor_token
        self.check_session_callback = check_session_callback
        self.default_ha_url = "http://supervisor/core"
        
        self.log_prefix = f"API PROXY [{self.session_id}]:"

    def log(self, message):
        print(f"{self.log_prefix} {message}", flush=True)

    async def run(self):
        """
        Connects to the emulator's API port and listens for Home Assistant service calls.
        When a call is received, it's forwarded to the actual Home Assistant instance.
        """
        self.log(f"Starting proxy (target port {self.port})...")
        
        # Wait for the emulator to start and listen on the port
        client = APIClient(
            address="127.0.0.1",
            port=self.port,
            password="",
        )

        # Capture main loop for thread-safe scheduling
        try:
            main_loop = asyncio.get_running_loop()
        except RuntimeError:
            # Should not happen as we are in async run
            main_loop = asyncio.new_event_loop()

        def fetch_and_send_ha_state_wrapped(entity_id, attribute):
            """Fetch state from HA and send to emulator. Runs in executor thread."""
            try:
                # Determine URL/Header
                if self.ha_url and self.ha_url.strip():
                    url = f"{self.ha_url.rstrip('/')}/api/states/{entity_id}"
                    headers = {"Content-Type": "application/json"}
                    if self.ha_token:
                        headers["Authorization"] = f"Bearer {self.ha_token}"
                else:
                    if not self.supervisor_token:
                        return
                    url = f"{self.default_ha_url}/api/states/{entity_id}"
                    headers = {
                        "Authorization": f"Bearer {self.supervisor_token}",
                        "Content-Type": "application/json",
                    }

                # self.log(f"Fetching state for {entity_id}")
                try:
                    res = requests.get(url, headers=headers, timeout=5)
                except requests.exceptions.RequestException:
                    # Silent fail on connection error to avoid log spam? or log it?
                    return

                if res.status_code == 200:
                    data = res.json()
                    state = data.get("state", "")
                    
                    # If specific attribute requested
                    if attribute:
                        val = data.get("attributes", {}).get(attribute, "")
                        state = str(val) if val is not None else ""
                    
                    self.log(f"Sending state {entity_id} = {state} (attr: {attribute})")
                    
                    # Schedule sending on main loop
                    async def send():
                        try:
                            # client.send_home_assistant_state is a coroutine? No, usually sync method that schedules on the loop?
                            # In aioesphomeapi, it sends a message. 
                            # Let's check signature. It seems to be synchronous in the library but sends over the connection.
                            # But since we are not on the loop thread in this executor, we need to be careful.
                            # If it's not thread safe, we must schedule it.
                            # But if it's async, we must await it.
                            # send_home_assistant_state sends a HomeAssistantStateResponse. 
                            # It is a synchronous method in the APIClient class that calls send_message.
                            client.send_home_assistant_state(entity_id, attribute, state)
                        except Exception as ex:
                            self.log(f"Error sending update via client: {ex}")
                    
                    # send() is async def, so we use run_coroutine_threadsafe
                    asyncio.run_coroutine_threadsafe(send(), main_loop)
                    
                else:
                    self.log(f"Failed to fetch state {entity_id}: {res.status_code}")
                    
            except Exception as e:
                self.log(f"Error fetching state {entity_id}: {e}")

        def handle_state_sub(entity_id, attribute):
            """Callback when device subscribes to a state."""
            self.log(f"Subscription request for {entity_id} (attr: {attribute})")
            # Run fetch in background thread so we don't block the async loop
            if main_loop:
                 main_loop.run_in_executor(None, lambda: fetch_and_send_ha_state_wrapped(entity_id, attribute))

        def on_device_state(state):
            # Just log device states
            pass

        def handle_service_call(call):
            """
            Handle the service call. 
            Note: call is a HomeassistantServiceCall object.
            """
            self.log(f"DEBUG: Service Call Object: {call!r}")
            # We need to split service into domain and service_name
            if '.' in call.service:
                domain, service_name = call.service.split('.', 1)
            else:
                domain = "homeassistant"
                service_name = call.service

            self.log(f"Service call received: {domain}.{service_name}")
            self.log(f"Data: {call.data}")
            
            # Determine target URL and Token for HA
            if self.ha_url and self.ha_url.strip():
                # Remote HA mode
                url = f"{self.ha_url.rstrip('/')}/api/services/{domain}/{service_name}"
                headers = {
                    "Content-Type": "application/json",
                }
                if self.ha_token:
                    headers["Authorization"] = f"Bearer {self.ha_token}"
            else:
                # Local HA mode (Supervisor)
                if not self.supervisor_token:
                    self.log("Error - SUPERVISOR_TOKEN not set")
                    return
                     
                url = f"{self.default_ha_url}/api/services/{domain}/{service_name}"
                headers = {
                    "Authorization": f"Bearer {self.supervisor_token}",
                    "Content-Type": "application/json",
                }

            try:
                # Merge data, data_template and variables
                payload = {**call.data, **call.data_template, **call.variables}
                
                self.log(f"Forwarding to {url} with payload: {payload}")
                
                res = requests.post(url, headers=headers, json=payload, timeout=10)
                
                self.log(f"HA Response [{res.status_code}]: {res.text}")
                
                if res.status_code not in [200, 201]:
                     self.log("WARNING - HA rejected the call!")
                     
            except Exception as e:
                self.log(f"Error forwarding service call: {str(e)}")

        # Wrap the sync handler to be called from the event loop using an executor
        def on_service_call_callback(call):
            if main_loop:
                 main_loop.run_in_executor(None, handle_service_call, call)

        max_retries = 120 # Try for 10 minutes total (5s * 120)
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if not self.check_session_callback():
                    self.log("Session removed, stopping proxy")
                    return

                self.log(f"Attempting connection (Attempt {retry_count + 1}/{max_retries})...")
                await client.connect(login=True)
                self.log("Connected to emulator API")
                
                # Subscribe to Home Assistant service calls and states
                client.subscribe_home_assistant_states_and_services(
                    on_state=on_device_state,
                    on_service_call=on_service_call_callback,
                    on_state_sub=handle_state_sub,
                    on_state_request=handle_state_sub
                )
                
                # Reset retry count once connected
                retry_count = 0
                
                # Keep the proxy running as long as the session checks out
                while True:
                    if not self.check_session_callback():
                        return
                    await asyncio.sleep(5)
                    
            except Exception as e:
                retry_count += 1
                self.log(f"Connection failed or lost: {str(e)}. Retrying in 5s...")
                try:
                    await client.disconnect()
                except:
                    pass
                await asyncio.sleep(5)
                
        self.log(f"Failed to connect after {max_retries} attempts. Giving up.")

def run_proxy_thread(session_id, port, ha_url, ha_token, supervisor_token, check_session_callback):
    """Entry point for the proxy thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    proxy = HAProxy(session_id, port, ha_url, ha_token, supervisor_token, check_session_callback)
    try:
        loop.run_until_complete(proxy.run())
    except Exception as e:
        print(f"API PROXY [{session_id}]: Thread error: {str(e)}", flush=True)
    finally:
        loop.close()
