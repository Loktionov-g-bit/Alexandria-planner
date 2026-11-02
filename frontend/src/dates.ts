// Date formatting for every interface language.
// Chrome ships ICU data for ru/en/de/cs, but not for be and ka, and kk comes out as "M11 2".
// Those three get their own month and weekday names here; the rest use Intl.

type Table = { short: string[]; long: string[]; days: string[]; now: string; min: string; hour: string; day: string }

const OWN: Record<string, Table> = {
  be: {
    short: ['студз.', 'лют.', 'сак.', 'крас.', 'трав.', 'чэрв.', 'ліп.', 'жн.', 'вер.', 'кастр.', 'ліст.', 'снеж.'],
    long: ['студзень', 'люты', 'сакавік', 'красавік', 'травень', 'чэрвень', 'ліпень', 'жнівень', 'верасень', 'кастрычнік', 'лістапад', 'снежань'],
    days: ['пн', 'аў', 'ср', 'чц', 'пт', 'сб', 'нд'],
    now: 'толькі што', min: '{n} хв таму', hour: '{n} гадз таму', day: '{n} дз таму',
  },
  kk: {
    short: ['қаң.', 'ақп.', 'нау.', 'сәу.', 'мам.', 'мау.', 'шіл.', 'там.', 'қыр.', 'қаз.', 'қар.', 'жел.'],
    long: ['қаңтар', 'ақпан', 'наурыз', 'сәуір', 'мамыр', 'маусым', 'шілде', 'тамыз', 'қыркүйек', 'қазан', 'қараша', 'желтоқсан'],
    days: ['дс', 'сс', 'ср', 'бс', 'жм', 'сб', 'жс'],
    now: 'қазір', min: '{n} мин бұрын', hour: '{n} сағ бұрын', day: '{n} күн бұрын',
  },
  ka: {
    short: ['იან', 'თებ', 'მარ', 'აპრ', 'მაი', 'ივნ', 'ივლ', 'აგვ', 'სექ', 'ოქტ', 'ნოე', 'დეკ'],
    long: ['იანვარი', 'თებერვალი', 'მარტი', 'აპრილი', 'მაისი', 'ივნისი', 'ივლისი', 'აგვისტო', 'სექტემბერი', 'ოქტომბერი', 'ნოემბერი', 'დეკემბერი'],
    days: ['ორშ', 'სამ', 'ოთხ', 'ხუთ', 'პარ', 'შაბ', 'კვი'],
    now: 'ახლახან', min: '{n} წთ წინ', hour: '{n} სთ წინ', day: '{n} დღის წინ',
  },
}

/** A locale Intl handles well: own-table languages borrow digits and offsets from English. */
export const intlLang = (lang: string) => (OWN[lang] ? 'en-GB' : lang)

const two = (n: number) => String(n).padStart(2, '0')
const hm = (d: Date) => `${two(d.getHours())}:${two(d.getMinutes())}`
const parse = (iso: string) => new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''))

/** "2 нояб.", "Nov 2", "2 ліст." */
export function shortDate(iso: string, lang: string) {
  const d = parse(iso)
  const own = OWN[lang]
  return own ? `${d.getDate()} ${own.short[d.getMonth()]}` : d.toLocaleDateString(lang, { day: 'numeric', month: 'short' })
}

/** "2 нояб., 10:45" */
export function dateTime(iso: string, lang: string) {
  const d = parse(iso)
  return OWN[lang] ? `${shortDate(iso, lang)}, ${hm(d)}` : d.toLocaleString(lang, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/** "Ноябрь 2026" for archive piles; key is "2026-11". */
export function monthYear(key: string, lang: string) {
  const d = parse(`${key}-01`)
  const own = OWN[lang]
  const name = own ? `${own.long[d.getMonth()]} ${d.getFullYear()}` : d.toLocaleDateString(lang, { month: 'long', year: 'numeric' }).replace(' г.', '')
  return name[0].toUpperCase() + name.slice(1)
}

/** Short weekday names, Monday first. */
export function weekdays(lang: string) {
  return OWN[lang]?.days ?? [1, 2, 3, 4, 5, 6, 7].map((i) => new Date(2026, 10, 1 + i).toLocaleDateString(lang, { weekday: 'short' }))
}

/** "02.11.2026, 10:45:12" for the sign-in log. */
export function stamp(iso: string, lang: string) {
  const d = new Date(iso)
  if (!OWN[lang]) return new Intl.DateTimeFormat(lang, { dateStyle: 'short', timeStyle: 'medium' }).format(d)
  return `${two(d.getDate())}.${two(d.getMonth() + 1)}.${d.getFullYear()}, ${hm(d)}:${two(d.getSeconds())}`
}

/** "5 мин назад", "вчера" */
export function ago(iso: string, lang: string) {
  const s = (new Date(iso).getTime() - Date.now()) / 1000
  const own = OWN[lang]
  if (own) {
    const n = (v: number, tpl: string) => tpl.replace('{n}', String(Math.max(1, Math.round(-v))))
    if (s > -60) return own.now
    if (s > -3600) return n(s / 60, own.min)
    if (s > -86400) return n(s / 3600, own.hour)
    return n(s / 86400, own.day)
  }
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })
  if (s > -60) return rtf.format(Math.round(s), 'second')
  if (s > -3600) return rtf.format(Math.round(s / 60), 'minute')
  if (s > -86400) return rtf.format(Math.round(s / 3600), 'hour')
  return rtf.format(Math.round(s / 86400), 'day')
}
