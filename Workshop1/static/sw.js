 "use strict";


 self.addEventListener("install", () => self.skipWaiting());

 self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

 self.addEventListener("notificationclick", (event) => {

   event.notification.close();

   const targetUrl = event.notification.data?.url || "/";



   event.waitUntil((async () => {

     const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });

     for (const client of windows) {

       if ("focus" in client) {

         await client.focus();

         if ("navigate" in client) await client.navigate(targetUrl);

         return;

       }

     }

     if (self.clients.openWindow) await self.clients.openWindow(targetUrl);

   })());

 });