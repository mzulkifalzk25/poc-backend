from scripts.seed.demo_tenant import SeedResult
from scripts.seed.sample_data import OWNER_USERNAME


def summary_lines(result: SeedResult) -> list[str]:
    lines = [
        f"Seeded {result.tenant.name} (tenant {result.tenant.id}), "
        f"{result.product_count} products.",
        f"Owner login: {OWNER_USERNAME}  password: {result.owner_password}",
        "Cashier PINs:",
    ]
    lines += [f"  {name}: {pin}" for name, pin in result.pins.items()]
    lines.append("Device tokens (Authorization: Device <token>):")
    lines += [f"  Counter {code}: {token}" for code, token in result.device_tokens.items()]
    lines.append("Activation codes (single use, 15 minutes):")
    lines += [
        f"  Counter {code}: {issued.code} (expires {issued.expires_at:%H:%M:%S} UTC)"
        for code, issued in result.activation_codes.items()
    ]
    return lines
