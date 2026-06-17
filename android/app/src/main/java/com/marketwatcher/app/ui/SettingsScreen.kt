package com.marketwatcher.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
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
import com.marketwatcher.app.data.AppSettings
import kotlinx.coroutines.launch

/** Configure the backend (base URL + dashboard token) and test connectivity. */
@Composable
fun SettingsScreen(settings: AppSettings, onSaved: () -> Unit) {
    var url by remember { mutableStateOf(settings.baseUrl) }
    var token by remember { mutableStateOf(settings.dashboardToken) }
    var status by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    Column(Modifier.padding(16.dp)) {
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text("URL do backend (via VPN)") },
        )
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            label = { Text("Dashboard token") },
        )
        Button(onClick = {
            settings.baseUrl = url.trim()
            settings.dashboardToken = token.trim()
            onSaved()
            status = "Salvo"
        }) { Text("Salvar") }
        Button(onClick = {
            scope.launch {
                status = runCatching {
                    "OK: ${settings.api().proposals().size} propostas"
                }.getOrElse { "Erro: ${it.message}" }
            }
        }) { Text("Testar conexão") }
        if (status.isNotEmpty()) Text(status, Modifier.padding(top = 8.dp))
    }
}
