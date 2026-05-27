import { contextBridge } from 'electron'

const FLASK_PORT = 5174

contextBridge.exposeInMainWorld('api', {
  flaskPort: FLASK_PORT,
  flaskBase: `http://127.0.0.1:${FLASK_PORT}`,
})
