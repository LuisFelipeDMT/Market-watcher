package com.marketwatcher.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.marketwatcher.app.data.MarketWatcherApi
import com.marketwatcher.app.data.Proposal

/** The unified ranked feed. Tapping a card would open detail (TODO). */
@Composable
fun ProposalsScreen(api: MarketWatcherApi, onSelect: (Proposal) -> Unit) {
    var proposals by remember { mutableStateOf<List<Proposal>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        try {
            proposals = api.proposals()
        } catch (e: Exception) {
            error = e.message
        }
    }

    error?.let { Text("Erro: $it", Modifier.padding(16.dp)); return }

    LazyColumn(Modifier.padding(8.dp)) {
        items(proposals) { p ->
            Card(Modifier.padding(8.dp).clickable { onSelect(p) }) {
                Column(Modifier.padding(12.dp)) {
                    Text(p.title)
                    Text(p.subtitle)
                    FlowRow {
                        p.metrics.forEach { (k, v) ->
                            AssistChip(onClick = {}, label = { Text("$k $v") })
                        }
                    }
                    p.reasons.take(2).forEach { Text("• $it") }
                    Text(p.action)
                }
            }
        }
    }
}
