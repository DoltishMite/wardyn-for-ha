// Seals a test link copy exactly as Wardyn's page does (web/siteline/wardyn/hass.js: "wardyn-" keys, gzip, AES-GCM), with a test code:
//   node tests/make_vector.mjs > tests/vector.json
const enc = new TextEncoder();
const code = 'TEST-C0DE-0000-1111-2222', c = code.replace(/-/g, '');
const key = await crypto.subtle.importKey('raw', await crypto.subtle.digest('SHA-256', enc.encode('wardyn-key:' + c)), 'AES-GCM', false, ['encrypt']);
const id = Buffer.from(await crypto.subtle.digest('SHA-256', enc.encode('wardyn-id:' + c))).toString('hex');
const doc = { format: 1, wardyn: 1, name: 'Wardyn', by: 'page', state: { v: 1, nodes: {}, nets: {} }, presence: [], newdevs: [], requests: [], done: {} };
const gz = new Uint8Array(await new Response(new Blob([enc.encode(JSON.stringify(doc))]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
const iv = crypto.getRandomValues(new Uint8Array(12));
const sealed = `1.z.${Buffer.from(iv).toString('base64')}.${Buffer.from(new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, gz))).toString('base64')}`;
console.log(JSON.stringify({ code, id, doc: sealed }, null, 1));
