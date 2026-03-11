const CREDIT_UNITS_PER_CREDIT = 100;
const USD_PER_CREDIT = 0.008;

const creditFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

const usdFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

export function creditUnitsToCredits(units: number): number {
  return units / CREDIT_UNITS_PER_CREDIT;
}

export function formatCredits(units: number): string {
  return creditFormatter.format(creditUnitsToCredits(units));
}

export function billedUsdFromCreditUnits(units: number): number {
  return creditUnitsToCredits(units) * USD_PER_CREDIT;
}

export function formatBilledUsd(units: number): string {
  return usdFormatter.format(billedUsdFromCreditUnits(units));
}

export function formatRawUsd(usd: number): string {
  return usdFormatter.format(usd);
}

export function usesMinimumChargeFloor(units: number, rawUsd: number | null | undefined): boolean {
  if (rawUsd == null) {
    return false;
  }
  return billedUsdFromCreditUnits(units) - rawUsd > 0.000001;
}