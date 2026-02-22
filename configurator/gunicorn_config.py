import logging
import gunicorn.glogging

class CustomGunicornLogger(gunicorn.glogging.Logger):
    def access(self, resp, req, environ, request_time):
        # Filter out /api/emulator/status successful requests
        if req.path == "/api/emulator/status" and resp.status == "200":
            return
        super().access(resp, req, environ, request_time)

logger_class = CustomGunicornLogger
accesslog = '-'
errorlog = '-'
