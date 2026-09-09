// Entrada para el Bot Console Manager: no es un bot de Discord, es la
// Tienda pública del Piano Autoplayer (piano_tienda_server.py). Este
// archivo solo lanza ese script de Python y lo reinicia solo si se cae,
// para que se vea y se controle igual que tus otros bots (Iniciar /
// Pausar / Detener), sin depender de dejar una consola de PowerShell
// abierta a mano.
const { spawn } = require('child_process');
const path = require('path');

const SCRIPT = path.join(__dirname, 'piano_tienda_server.py');
// Si "python" no es el comando correcto en esta PC, puedes forzarlo con
// la variable de entorno PYTHON_BIN antes de abrir el Bot Console
// Manager (ej. PYTHON_BIN=py, o la ruta completa a python.exe).
const PYTHON = process.env.PYTHON_BIN || 'python';

let detenido = false;

function iniciarServidor() {
  console.log(`[Piano Tienda] Iniciando ${SCRIPT} con "${PYTHON}"...`);
  const proc = spawn(PYTHON, [SCRIPT], {
    cwd: __dirname,
    shell: true,
  });

  proc.stdout.on('data', (data) => process.stdout.write(`[Piano Tienda] ${data}`));
  proc.stderr.on('data', (data) => process.stderr.write(`[Piano Tienda] ${data}`));

  proc.on('error', (err) => {
    console.log(`[Piano Tienda] No se pudo iniciar Python: ${err.message}`);
  });

  proc.on('close', (code) => {
    if (detenido) return;
    console.log(`[Piano Tienda] El servidor de Python se cerró (código ${code}). Reintentando en 3s...`);
    setTimeout(iniciarServidor, 3000);
  });
}

process.on('SIGINT', () => { detenido = true; process.exit(0); });
process.on('SIGTERM', () => { detenido = true; process.exit(0); });

iniciarServidor();
