package com.marketwatcher.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.marketwatcher.app.data.MarketWatcherApi
import com.marketwatcher.app.data.Proposal

private enum class Phase { LOADING, ERROR, EMPTY, READY }

/** The unified ranked feed, with loading / empty / error states + refresh. */
@Composable
fun ProposalsScreen(api: MarketWatcherApi, onSelect: (Proposal) -> Unit) {
    var proposals by remember { mutableStateOf<List<Proposal>>(emptyList()) }
    var phase by remember { mutableStateOf(Phase.LOADING) }
    var error by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }

    androidx.compose.runtime.LaunchedEffect(reload) {
        phase = Phase.LOADING
        try {
            proposals = api.proposals()
            phase = if (proposals.isEmpty()) Phase.EMPTY else Phase.READY
        } catch (e: Exception) {
            error = e.message ?: "falha de rede"
            phase = Phase.ERROR
        }
    }

    // Auto-refresh the feed every 60s while the screen is shown.
    androidx.compose.runtime.LaunchedEffect(Unit) {
        while (true) {
            kotlinx.coroutines.delay(60_000)
            reload++
        }
    }

    when (phase) {
        Phase.LOADING -> Box(Modifier.fillMaxSize(), Alignment.Center) {
            CircularProgressIndicator()
        }
        Phase.ERROR -> Column(Modifier.padding(16.dp)) {
            Text("Erro: $error")
            Button(onClick = { reload++ }) { Text("Tentar novamente") }
        }
        Phase.EMPTY -> Column(Modifier.padding(16.dp)) {
            Text("Nenhuma proposta no momento")
            Button(onClick = { reload++ }) { Text("Atualizar") }
        }
        Phase.READY -> LazyColumn(Modifier.padding(8.dp)) {
            item {
                Button(onClick = { reload++ }, Modifier.padding(8.dp)) { Text("Atualizar") }
            }
            items(proposals) { p ->
                Card(Modifier.padding(8.dp).clickable { onSelect(p) }) {
                    Column(Modifier.padding(12.dp), Arrangement.spacedBy(4.dp)) {
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
}
