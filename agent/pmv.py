
import logging
import math
from functools import lru_cache

logger = logging.getLogger(__name__)

MET_OFFICE_WORK = 1.1  
CLO_OFFICE_TYPICAL = 0.6  
AIR_VELOCITY_MS = 0.1


AIR_TEMP_RANGE_C = (-30.0, 60.0)
RH_RANGE_PCT = (0.0, 100.0)
NEUTRAL_PMV_FALLBACK = 0.0


def pmv(air_temp_c: float, mean_radiant_temp_c: float, relative_humidity_pct: float,
        met: float = MET_OFFICE_WORK, clo: float = CLO_OFFICE_TYPICAL,
        air_velocity_ms: float = AIR_VELOCITY_MS) -> float:
    
    clamped_temp = min(max(air_temp_c, AIR_TEMP_RANGE_C[0]), AIR_TEMP_RANGE_C[1])
    clamped_mrt = min(max(mean_radiant_temp_c, AIR_TEMP_RANGE_C[0]), AIR_TEMP_RANGE_C[1])
    clamped_rh = min(max(relative_humidity_pct, RH_RANGE_PCT[0]), RH_RANGE_PCT[1])

    result = _pmv_cached(
        round(clamped_temp, 1), round(clamped_mrt, 1), round(clamped_rh, 1), met, clo, air_velocity_ms
    )
    if not math.isfinite(result):
        logger.error(
            "pmv() produced a non-finite result for air_temp_c=%s mean_radiant_temp_c=%s "
            "relative_humidity_pct=%s - falling back to neutral PMV %.1f",
            air_temp_c, mean_radiant_temp_c, relative_humidity_pct, NEUTRAL_PMV_FALLBACK,
        )
        return NEUTRAL_PMV_FALLBACK
    return result


@lru_cache(maxsize=4096)
def _pmv_cached(air_temp_c: float, mean_radiant_temp_c: float, relative_humidity_pct: float,
                met: float, clo: float, air_velocity_ms: float) -> float:
    pa = relative_humidity_pct * 10.0 * math.exp(16.6536 - 4030.183 / (air_temp_c + 235.0))

    icl = 0.155 * clo
    m = met * 58.15
    mw = m

    fcl = 1.05 + 0.645 * icl if icl > 0.078 else 1.0 + 1.29 * icl

    hcf = 12.1 * math.sqrt(air_velocity_ms)
    taa = air_temp_c + 273.0
    tra = mean_radiant_temp_c + 273.0
    tcla = taa + (35.5 - air_temp_c) / (3.5 * icl + 0.1)

    p1 = icl * fcl
    p2 = p1 * 3.96
    p3 = p1 * 100.0
    p4 = p1 * taa
    p5 = 308.7 - 0.028 * mw + p2 * (tra / 100.0) ** 4

    xn = tcla / 100.0
    xf = tcla / 100.0
    hc = hcf
    for _ in range(150):
        xf = (xf + xn) / 2.0
        hcn = 2.38 * abs(100.0 * xf - taa) ** 0.25
        hc = hcf if hcf > hcn else hcn
        xn = (p5 + p4 * hc - p2 * xf ** 4) / (100.0 + p3 * hc)
        if abs(xn - xf) <= 0.00015:
            break

    tcl = 100.0 * xn - 273.0

    hl1 = 3.05 * 0.001 * (5733.0 - 6.99 * mw - pa)
    hl2 = 0.42 * (mw - 58.15) if mw > 58.15 else 0.0
    hl3 = 1.7 * 0.00001 * m * (5867.0 - pa)
    hl4 = 0.0014 * m * (34.0 - air_temp_c)
    hl5 = 3.96 * fcl * (xn ** 4 - (tra / 100.0) ** 4)
    hl6 = fcl * hc * (tcl - air_temp_c)

    ts = 0.303 * math.exp(-0.036 * m) + 0.028
    return ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)


def ppd(pmv_value: float) -> float:
    return 100.0 - 95.0 * math.exp(-0.03353 * pmv_value ** 4 - 0.2179 * pmv_value ** 2)
