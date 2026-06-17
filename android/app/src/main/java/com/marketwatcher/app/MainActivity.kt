package com.marketwatcher.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
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
import com.marketwatcher.app.data.Proposal
import com.marketwatcher.app.ui.ProposalDetailScreen
import com.marketwatcher.app.ui.ProposalsScreen
import com.marketwatcher.app.ui.SettingsScreen
import com.marketwatcher.app.ui.TwoFactorScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val settings = AppSettings(this)
        setContent {
            MaterialTheme {
                var tab by remember { mutableStateOf(0) }
                var selected by remember { mutableStateOf<Proposal?>(null) }
                // Rebuild the API client whenever the backend config changes.
                var configRev by remember { mutableStateOf(0) }
                val api = remember(configRev) { settings.api() }

                Scaffold(
                    bottomBar = {
                        NavigationBar {
                            NavigationBarItem(
                                selected = tab == 0,
                                onClick = { tab = 0; selected = null },
                                icon = {},
                                label = { Text("Propostas") },
                            )
                            NavigationBarItem(
                                selected = tab == 1,
                                onClick = { tab = 1 },
                                icon = {},
                                label = { Text("2FA") },
                            )
                            NavigationBarItem(
                                selected = tab == 2,
                                onClick = { tab = 2 },
                                icon = {},
                                label = { Text("Config") },
                            )
                        }
                    }
                ) { pad ->
                    Box(Modifier.padding(pad)) {
                        when (tab) {
                            0 -> {
                                val current = selected
                                if (current == null) {
                                    ProposalsScreen(api) { selected = it }
                                } else {
                                    ProposalDetailScreen(current) { selected = null }
                                }
                            }
                            1 -> TwoFactorScreen(api)
                            else -> SettingsScreen(settings) { configRev++ }
                        }
                    }
                }
            }
        }
    }
}
