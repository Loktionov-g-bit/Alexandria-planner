// Every locale must have exactly the keys of ru.json and the same {{placeholders}} in each string.
import { readFileSync, readdirSync } from 'node:fs'
const dir = new URL('../src/locales/', import.meta.url)
const flat = (o, p = '') => Object.entries(o).flatMap(([k, v]) => (v && typeof v === 'object' && !Array.isArray(v) ? flat(v, `${p}${k}.`) : [[p + k, v]]))
const vars = (s) => JSON.stringify(s).match(/\{\{\w+\}\}/g)?.sort().join() ?? ''
const ru = new Map(flat(JSON.parse(readFileSync(new URL('ru.json', dir)))))
let bad = 0
for (const f of readdirSync(dir).filter((f) => f.endsWith('.json') && f !== 'ru.json')) {
  const m = new Map(flat(JSON.parse(readFileSync(new URL(f, dir)))))
  const errs = []
  for (const [k, v] of ru) {
    if (!m.has(k)) errs.push(`missing ${k}`)
    else if (vars(m.get(k)) !== vars(v)) errs.push(`placeholders ${k}`)
    else if (Array.isArray(v) && m.get(k).length !== v.length) errs.push(`array length ${k}`)
  }
  for (const k of m.keys()) if (!ru.has(k)) errs.push(`extra ${k}`)
  console.log(f, errs.length ? errs : 'ok')
  bad += errs.length
}
process.exit(bad ? 1 : 0)
