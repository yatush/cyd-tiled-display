import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'
import yaml from 'js-yaml'
import { fileURLToPath } from 'url'
import { spawn } from 'child_process'

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const MOCK_ENTITIES = [
  { entity_id: 'mock.light_living_room', state: 'on', attributes: { friendly_name: 'Living Room Light' } },
  { entity_id: 'mock.light_kitchen', state: 'off', attributes: { friendly_name: 'Kitchen Light' } },
  { entity_id: 'mock.switch_coffee_maker', state: 'off', attributes: { friendly_name: 'Coffee Maker' } },
  { entity_id: 'mock.sensor_temperature', state: '22.5', attributes: { friendly_name: 'Temperature', unit_of_measurement: '°C' } },
  { entity_id: 'mock.sensor_humidity', state: '45', attributes: { friendly_name: 'Humidity', unit_of_measurement: '%' } },
  { entity_id: 'mock.binary_sensor_front_door', state: 'off', attributes: { friendly_name: 'Front Door' } },
  { entity_id: 'mock.media_player_tv', state: 'playing', attributes: { friendly_name: 'TV' } },
  { entity_id: 'mock.climate_living_room', state: 'heat', attributes: { friendly_name: 'Thermostat' } },
  { entity_id: 'mock.vacuum_robovac', state: 'docked', attributes: { friendly_name: 'RoboVac' } },
  { entity_id: 'mock.lock_front_door', state: 'locked', attributes: { friendly_name: 'Front Door Lock' } },
  { entity_id: 'mock.fan_bedroom', state: 'on', attributes: { friendly_name: 'Bedroom Fan', percentage: 50 } },
  { entity_id: 'mock.cover_garage_door', state: 'closed', attributes: { friendly_name: 'Garage Door' } },
  { entity_id: 'mock.media_player_living_room_speaker', state: 'idle', attributes: { friendly_name: 'Living Room Speaker' } },
  { entity_id: 'mock.input_boolean_guest_mode', state: 'off', attributes: { friendly_name: 'Guest Mode' } },
  { entity_id: 'mock.sun_sun', state: 'above_horizon', attributes: { friendly_name: 'Sun' } },
  { entity_id: 'mock.weather_home', state: 'sunny', attributes: { friendly_name: 'Home Weather', temperature: 25 } },
];

// Custom plugin to serve scripts from lib.yaml
const scriptsPlugin = () => ({
  name: 'scripts-loader',
  configureServer(server) {
    server.middlewares.use('/api/ha', async (req, res, next) => {
      const haUrl = req.headers['x-ha-url'] as string;
      const haToken = req.headers['x-ha-token'] as string;
      const useMock = req.headers['x-ha-mock'] === 'true';

      if (useMock || (!haUrl && !haToken)) {
        if (req.url?.endsWith('/states')) {
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify(MOCK_ENTITIES));
          return;
        }
        res.statusCode = 401;
        res.end(JSON.stringify({ error: 'HA Credentials missing and mock mode disabled' }));
        return;
      }

      try {
        const baseUrl = haUrl.endsWith('/') ? haUrl.slice(0, -1) : haUrl;
        const targetUrl = `${baseUrl}${req.url?.replace(/^\/api\/ha/, '/api')}`;
        const response = await fetch(targetUrl, {
          headers: {
            'Authorization': `Bearer ${haToken}`,
            'Content-Type': 'application/json'
          }
        });
        
        if (!response.ok) {
            res.statusCode = response.status;
            res.end(await response.text());
            return;
        }

        const data = await response.json();
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify(data));
      } catch (e: any) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
    });

    server.middlewares.use('/api/generate', (req, res, next) => {
      if (req.method !== 'POST') {
        res.statusCode = 405;
        res.end('Method Not Allowed');
        return;
      }

      let body = '';
      req.on('data', chunk => {
        body += chunk.toString();
      });

      req.on('end', () => {
        try {
          const pythonProcess = spawn('python', [path.resolve(__dirname, 'generate_tiles_api.py')]);
          
          let output = '';
          let errorOutput = '';

          pythonProcess.stdin.write(body);
          pythonProcess.stdin.end();

          pythonProcess.stdout.on('data', (data) => {
            output += data.toString();
          });

          pythonProcess.stderr.on('data', (data) => {
            errorOutput += data.toString();
          });

          pythonProcess.on('close', (code) => {
            if (code !== 0 && !output) {
              res.statusCode = 500;
              res.end(JSON.stringify({ error: errorOutput || 'Python process failed' }));
              return;
            }
            res.setHeader('Content-Type', 'application/json');
            res.end(output);
          });
        } catch (e) {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: e.message }));
        }
      });
    });

    let esphomePlace = '/esphome';
    for (let i = 0; i < 10; ++i) {
      const schemaPath = path.resolve(__dirname, esphomePlace + '/custom_components/tile_ui/schema.json');
      if (fs.existsSync(schemaPath)) {
        break;
      }
      esphomePlace = '../' + esphomePlace;
    }
    server.middlewares.use('/api/schema', (req, res, next) => {
      try {
        const schemaPath = path.resolve(__dirname, esphomePlace + '/custom_components/tile_ui/schema.json');
        if (fs.existsSync(schemaPath)) {
            const schemaContent = fs.readFileSync(schemaPath, 'utf8');
            res.setHeader('Content-Type', 'application/json');
            res.end(schemaContent);
        } else {
            res.statusCode = 404;
            res.end(JSON.stringify({ error: 'schema.json not found' }));
        }
      } catch (e) {
        console.error(e);
        res.statusCode = 500;
        res.end(JSON.stringify({ error: 'Internal Server Error' }));
      }
    });

    server.middlewares.use('/api/scripts', (req, res, next) => {
      try {
        const libPath = path.resolve(__dirname, esphomePlace + '/lib/lib.yaml');
        if (!fs.existsSync(libPath)) {
           res.statusCode = 404;
           res.end(JSON.stringify({ error: 'lib.yaml not found' }));
           return;
        }
        const fileContents = fs.readFileSync(libPath, 'utf8');
        
        // Define custom schema for !secret tag
        const SecretType = new yaml.Type('!secret', {
          kind: 'scalar',
          construct: function (data) {
            return null; // We don't need the actual secret value for parsing scripts
          }
        });
        const LambdaType = new yaml.Type('!lambda', {
          kind: 'scalar',
          construct: function (data) {
            return null; 
          }
        });
        const IncludeType = new yaml.Type('!include', {
          kind: 'scalar',
          construct: function (data) {
            return null; 
          }
        });
        const SCHEMA = yaml.DEFAULT_SCHEMA.extend([SecretType, LambdaType, IncludeType]);

        const doc = yaml.load(fileContents, { schema: SCHEMA }) as any;
        
        const scripts = doc.script || [];
        
        const standardColors = [
            { id: 'Color::BLACK', value: '#000000' },
            { id: 'Color::WHITE', value: '#FFFFFF' },
            { id: 'Color::RED', value: '#FF0000' },
            { id: 'Color::GREEN', value: '#00FF00' },
            { id: 'Color::BLUE', value: '#0000FF' },
            { id: 'Color::YELLOW', value: '#FFFF00' },
            { id: 'Color::ORANGE', value: '#FFA500' },
            { id: 'Color::PURPLE', value: '#800080' },
        ];

        const colors = [
            ...(doc.color || []).map((c: any) => {
            let value = '#000000';
            if (c.hex) {
                // Assume BGR based on observation (blue=FF0000, yellow=00FFFF)
                // Convert BGR to RGB for CSS
                const hex = c.hex.replace('#', '');
                if (hex.length === 6) {
                    const r = hex.substring(4, 6);
                    const g = hex.substring(2, 4);
                    const b = hex.substring(0, 2);
                    value = `#${r}${g}${b}`;
                } else {
                    value = '#' + hex;
                }
            } else if (c.red !== undefined && c.green !== undefined && c.blue !== undefined) {
                // For percentage/rgb values, assume they are correct RGB
                // If they are numbers (0-1 or 0-255) or strings with %
                const fmt = (v: any) => typeof v === 'number' && v <= 1 ? v * 100 + '%' : v;
                value = `rgb(${fmt(c.red)}, ${fmt(c.green)}, ${fmt(c.blue)})`;
            }
            return { id: c.id, value };
        }),
        ...standardColors];
        
        // Read fonts from base file (assuming 3248s035_base.yaml for now, or we could scan all)
        let fonts: string[] = [];
        try {
            const baseYamlPath = path.resolve(__dirname, esphomePlace + '/lib/3248s035_base.yaml');
            if (fs.existsSync(baseYamlPath)) {
                const baseContent = fs.readFileSync(baseYamlPath, 'utf8');
                const baseDoc = yaml.load(baseContent, { schema: SCHEMA }) as any;
                if (baseDoc.font) {
                    fonts = baseDoc.font.map((f: any) => f.id);
                }
            }
        } catch (e) { console.error("Error reading fonts", e); }

        // Read icons from mdi_glyphs.yaml
        let icons: { value: string, label: string, char?: string }[] = [];
        try {
            const glyphsPath = path.resolve(__dirname, esphomePlace + '/lib/mdi_glyphs.yaml');
            if (fs.existsSync(glyphsPath)) {
                const glyphsContent = fs.readFileSync(glyphsPath, 'utf8');
                
                // Manual parsing to extract comments as labels
                const lines = glyphsContent.split('\n');
                lines.forEach(line => {
                    // Match format: "HEX", # Comment
                    const match = line.match(/"\\U([0-9a-fA-F]+)",\s*#\s*(.*)/);
                    if (match) {
                        const hex = match[1];
                        const label = match[2].trim();
                        try {
                            const char = String.fromCodePoint(parseInt(hex, 16));
                            const value = `\\U${hex}`;
                            icons.push({ value, label, char });
                        } catch (e) {
                            // ignore invalid code points
                        }
                    }
                });

                // Fallback: if manual parsing found nothing, try standard YAML load
                if (icons.length === 0) {
                    const glyphsDoc = yaml.load(glyphsContent, { schema: SCHEMA }) as any;
                    if (Array.isArray(glyphsDoc)) {
                        icons = glyphsDoc.map((i: string) => ({ value: i, label: 'Icon', char: i }));
                    }
                }
            }
        } catch (e) { console.error("Error reading icons", e); }

        const displayScripts: any[] = [];
        const actionScripts: string[] = [];

        scripts.forEach((s: any) => {
            if (s.id) {
                if (s.id.startsWith('tile_')) {
                    const params = s.parameters || {};
                    const paramList = Object.keys(params)
                        .filter(k => k !== 'x' && k !== 'y' && k !== 'entities') // Filter out context params
                        .map(k => ({ name: k, type: params[k] }));
                    
                    displayScripts.push({
                        id: s.id,
                        params: paramList
                    });
                } else {
                    actionScripts.push(s.id);
                }
            }
        });

        const globals = (doc.globals || [])
            .filter((g: any) => g.type === 'bool')
            .map((g: any) => g.id);

        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({ 
            display: displayScripts, 
            action: actionScripts,
            colors,
            fonts,
            icons,
            globals
        }));
      } catch (e: any) {
        console.error(e);
        res.statusCode = 500;
        res.end(JSON.stringify({ error: e.message }));
      }
    });
  }
});

// https://vitejs.dev/config/
export default defineConfig({
  base: './',
  plugins: [react(), scriptsPlugin()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
  },
})
