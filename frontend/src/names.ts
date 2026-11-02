// Same rules as backend/app/names.py: "Олег Журавлёв" → "o.zhuravlev", "Müller" → "mueller", "გიორგი" → "giorgi"
const MAP: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm',
  н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'shch',
  ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya', і: 'i', ї: 'yi', є: 'ye', ґ: 'g', ў: 'u',
  ә: 'a', ғ: 'g', қ: 'k', ң: 'n', ө: 'o', ұ: 'u', ү: 'u', һ: 'h',
  ა: 'a', ბ: 'b', გ: 'g', დ: 'd', ე: 'e', ვ: 'v', ზ: 'z', თ: 't', ი: 'i', კ: 'k', ლ: 'l', მ: 'm', ნ: 'n', ო: 'o',
  პ: 'p', ჟ: 'zh', რ: 'r', ს: 's', ტ: 't', უ: 'u', ფ: 'p', ქ: 'k', ღ: 'gh', ყ: 'q', შ: 'sh', ჩ: 'ch', ც: 'ts',
  ძ: 'dz', წ: 'ts', ჭ: 'ch', ხ: 'kh', ჯ: 'j', ჰ: 'h',
  ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss',
}

export function translit(text: string) {
  const out = [...text.toLowerCase()].map((ch) => MAP[ch] ?? ch).join('').normalize('NFKD').replace(/\p{M}+/gu, '')
  return out.replace(/[\s_]*-[\s_-]*/g, '-').replace(/[^a-z0-9-]+/g, '').replace(/^-+|-+$/g, '')
}

export function baseLogin(first: string, last: string) {
  const f = translit(first)
  const l = translit(last)
  return (f && l ? `${f[0]}.${l}` : l || f).slice(0, 60)
}
