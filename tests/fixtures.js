// 測試用的小型資料(欄位與 data.js 建置輸出相同)
export function art(no, tags = {}, extra = {}) {
  return { no: String(no), name: `文 ${no}`, author: '作者A', translator: '', persona: '', alias: '',
    created: '', ck: 0, edited: '', ek: 0, links: [['Postype', 'https://x/' + no]], dead: false, tags, _s: `文 ${no} 作者a`, ...extra };
}
export const ARTICLES = [
  art(1, { 'CP配對': ['安/員'], '氛圍': ['甜文'], '結局': ['HE'] }, { ck: 202601010000 }),
  art(2, { 'CP配對': ['員/安'], '氛圍': ['甜文', '日常'] }, { ck: 202603010000, author: '作者B' }),
  art(3, { 'CP配對': ['安/員', '員/安'], '氛圍': ['虐文'] }, { ck: 202602010000, dead: true }),
  art(4, { 'CP配對': ['互攻'], '氛圍': ['日常'] }, { ck: 202603010000, translator: '譯者C' }),
  art(5, { 'CP配對': [], '氛圍': ['甜文', '日常'] }, { ck: 0, _s: '穿越 时间 作者a' }),
];
