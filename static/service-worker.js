self.addEventListener('install', function(event) {
  // You can cache files here if you want
  console.log('Service Worker installed');
});
self.addEventListener('fetch', function(event) {
  // You can serve cached files here if offline
});
