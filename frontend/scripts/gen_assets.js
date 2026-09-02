import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const idlePath = path.resolve(__dirname, '../assets/corgi_idle.png');
const runPath = path.resolve(__dirname, '../assets/corgi_run.png');
const outPath = path.resolve(__dirname, '../src/assets.ts');

const idleBase64 = fs.readFileSync(idlePath).toString('base64');
const runBase64 = fs.readFileSync(runPath).toString('base64');

const content = `// Auto-generated sprite base64 assets for JakeAI
export const SPRITE_IDLE_BASE64: string = 'data:image/png;base64,${idleBase64}';
export const SPRITE_RUN_BASE64: string = 'data:image/png;base64,${runBase64}';
`;

fs.writeFileSync(outPath, content, 'utf8');
console.log('Successfully generated src/assets.ts with size:', content.length);
