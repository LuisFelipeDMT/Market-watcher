package com.marketwatcher.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.marketwatcher.app.data.CodeBody
import com.marketwatcher.app.data.MarketWatcherApi
import com.marketwatcher.app.data.TwoFactorRequest
import kotlinx.coroutines.launch

/** Lists pending login approvals and relays the code from your authenticator. */
@Composable
fun TwoFactorScreen(api: MarketWatcherApi) {
    var pending by remember { mutableStateOf<List<TwoFactorRequest>>(emptyList()) }
    val scope = rememberCoroutineScope()

    suspend fun refresh() {
        pending = runCatching { api.pendingTwoFactor() }.getOrDefault(emptyList())
    }

    androidx.compose.runtime.LaunchedEffect(Unit) { refresh() }

    Column(Modifier.padding(12.dp)) {
        if (pending.isEmpty()) {
            Text("Nenhuma aprovação pendente")
        }
        pending.forEach { req ->
            var code by remember(req.id) { mutableStateOf("") }
            Card(Modifier.padding(8.dp)) {
                Column(Modifier.padding(12.dp)) {
                    Text(req.reason)
                    Text("expira: ${req.expires_at}")
                    OutlinedTextField(
                        value = code,
                        onValueChange = { code = it },
                        label = { Text("Código do autenticador") },
                    )
                    Row {
                        Button(onClick = {
                            scope.launch {
                                api.approve(req.id, CodeBody(code)); refresh()
                            }
                        }) { Text("Aprovar") }
                        Button(onClick = {
                            scope.launch { api.deny(req.id); refresh() }
                        }) { Text("Negar") }
                    }
                }
            }
        }
    }
}
