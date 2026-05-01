from __future__ import annotations


PUBLIC_MODEL_LABELS = {
    "V1_Standard": "Standard Risk Parity",
    "V1 Standard RP": "Standard Risk Parity",
    "Standard RP": "Standard Risk Parity",
    "V2_Relaxed": "Local Relaxed Risk Parity",
    "V2 Relaxed RRP": "Local Relaxed Risk Parity",
    "Relaxed RRP": "Local Relaxed Risk Parity",
    "V3_Global_RRP": "Global Relaxed Risk Parity",
    "V3 Global RRP": "Global Relaxed Risk Parity",
    "Global RRP": "Global Relaxed Risk Parity",
    "Dynamic_RRP": "Defensive Dynamic Relaxed Risk Parity",
    "Dynamic RRP": "Defensive Dynamic Relaxed Risk Parity",
    "Dynamic_RRP_before": "Defensive Dynamic RRP before overlay optimization",
    "Current_Dynamic_RRP": "Defensive Dynamic RRP before overlay optimization",
    "HRP": "HRP Benchmark",
    "HRP_Benchmark": "HRP Benchmark",
    "HERC": "HERC Benchmark",
    "HERC_Benchmark": "HERC Benchmark",
}


def public_model_label(name: object) -> str:
    text = str(name)
    if text in PUBLIC_MODEL_LABELS:
        return PUBLIC_MODEL_LABELS[text]
    text = text.replace("V3_Global_RRP", "Global Relaxed Risk Parity")
    text = text.replace("Dynamic_RRP_before", "Defensive Dynamic RRP before overlay optimization")
    text = text.replace("Dynamic_RRP", "Defensive Dynamic Relaxed Risk Parity")
    text = text.replace("V1_Standard", "Standard Risk Parity")
    text = text.replace("V2_Relaxed", "Local Relaxed Risk Parity")
    text = text.replace("HRP_Benchmark", "HRP Benchmark")
    text = text.replace("HERC_Benchmark", "HERC Benchmark")
    return text.replace("_", " ")


def apply_public_model_labels(df, column: str = "model"):
    out = df.copy()
    if column in out.columns:
        out[column] = out[column].map(public_model_label)
    return out
