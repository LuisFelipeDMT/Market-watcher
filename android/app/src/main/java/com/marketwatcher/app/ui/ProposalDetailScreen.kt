package com.marketwatcher.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Divider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.marketwatcher.app.data.Proposal

/** Full decision context for one proposal; you act manually in XP for now. */
@Composable
fun ProposalDetailScreen(p: Proposal, onBack: () -> Unit) {
    Column(Modifier.padding(16.dp).verticalScroll(rememberScrollState())) {
        Button(onClick = onBack) { Text("Voltar") }
        Text(p.title)
        Text(p.subtitle)
        Text("Score ${"%.0f".format(p.score)} · ${p.asset_class}")
        Divider(Modifier.padding(vertical = 8.dp))
        p.metrics.forEach { (k, v) -> Row { Text("$k: "); Text(v) } }
        if (p.reasons.isNotEmpty()) {
            Divider(Modifier.padding(vertical = 8.dp))
            Text("Por quê")
            p.reasons.forEach { Text("• $it") }
        }
        if (p.warnings.isNotEmpty()) {
            Divider(Modifier.padding(vertical = 8.dp))
            Text("Atenção")
            p.warnings.forEach { Text("⚠ $it") }
        }
        Divider(Modifier.padding(vertical = 8.dp))
        Text(p.action)
    }
}
