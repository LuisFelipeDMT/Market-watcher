package com.marketwatcher.app.push

// Enable with the Firebase dependency + google-services.json, then add the
// <service> entry in AndroidManifest.xml. Registers the device token with the
// gateway and surfaces alerts (opportunities, TRIGGERED names, 2FA) as
// notifications.
//
// import com.google.firebase.messaging.FirebaseMessagingService
// import com.google.firebase.messaging.RemoteMessage
//
// class PushService : FirebaseMessagingService() {
//     override fun onNewToken(token: String) {
//         // POST to /mobile/devices with this token (use AppSettings.api()).
//     }
//     override fun onMessageReceived(message: RemoteMessage) {
//         val n = message.notification ?: return
//         // Build a system notification from n.title / n.body; for a 2FA push
//         // (message.data["kind"] == "SECURITY" / 2FA), deep-link to the 2FA tab.
//     }
// }
