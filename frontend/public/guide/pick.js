// same origin as the app, so the app's saved language wins
var codes = ["ru", "en", "de", "cs", "be", "kk", "ka"], pick = null
try { pick = localStorage.getItem('lang') } catch (e) {}
if (codes.indexOf(pick) < 0) pick = (navigator.languages || [navigator.language]).map(function (l) { return l.slice(0, 2) }).filter(function (l) { return codes.indexOf(l) >= 0 })[0] || 'en'
location.replace(pick + '/' + location.hash)
