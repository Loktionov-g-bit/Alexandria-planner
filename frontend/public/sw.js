/* Alexandria Planner service worker: Web Push only. No offline caching on purpose:
   a stale cached app would talk to a newer server after an update. */
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))

self.addEventListener('push', (event) => {
  let data = {}
  try { data = event.data ? event.data.json() : {} } catch { data = { title: event.data && event.data.text() } }
  const title = data.title || 'Alexandria'
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || '',
    tag: data.tag || undefined,
    renotify: Boolean(data.tag),
    icon: 'alexandria-planner-logo-192.png',
    badge: 'alexandria-planner-logo-192.png',
    data: { url: new URL(data.url || './', self.registration.scope).href },
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data && event.notification.data.url
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const w of wins) {
      if (w.url.startsWith(self.registration.scope)) {
        await w.focus()
        if (url) w.navigate(url)
        return
      }
    }
    if (url) await self.clients.openWindow(url)
  })())
})
