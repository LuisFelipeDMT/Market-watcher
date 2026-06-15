package com.marketwatcher.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.marketwatcher.app.data.AppSettings
import com.marketwatcher.app.ui.ProposalsScreen
import com.marketwatcher.app.ui.TwoFactorScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val settings = AppSettings(this)
        setContent {
            MaterialTheme {
                var tab by remember { mutableStateOf(0) }
                val api = remember(settings.baseUrl, settings.dashboardToken) {
                    settings.api()
                }
                Scaffold(
                    bottomBar = {
                        NavigationBar {
                            NavigationBarItem(
                                selected = tab == 0,
                                onClick = { tab = 0 },
                                icon = {},
                                label = { Text("Propostas") },
                            )
                            NavigationBarItem(
                                selected = tab == 1,
                                onClick = { tab = 1 },
                                icon = {},
                                label = { Text("2FA") },
                            )
                        }
                    }
                ) { pad ->
                    androidx.compose.foundation.layout.Box(Modifier.padding(pad)) {
                        when (tab) {
                            0 -> ProposalsScreen(api)
                            else -> TwoFactorScreen(api)
                        }
                    }
                }
            }
        }
    }
}
