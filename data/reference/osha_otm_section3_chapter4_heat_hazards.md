# OSHA Technical Manual Section III: Chapter 4 - Heat Stress

Source: https://www.osha.gov/otm/section-3-health-hazards/chapter-4

## I. Introduction

The OSHA Technical Manual chapter addresses heat hazards in indoor and outdoor workplaces where temperatures exceed 70 degrees F and moderate workload activities occur. The document references the February 2016 NIOSH publication "Criteria for a Recommended Standard: Occupational Exposure to Heat and Hot Environments" as a technical resource for understanding heat stress and prevention strategies.

## II. Heat-Related Illness

### Definitions

**Heat Stress:** The combined net heat load from physical exertion, environmental factors, and clothing worn by workers.

**Heat Strain:** The physiological response of the body to heat stress, such as sweating and elevated heart rate.

### Heat-Related Illnesses

**Heat Stroke** - The most serious condition requiring emergency treatment. Body temperature rises rapidly (41C/106F or higher within 10-15 minutes), sweating may cease, and cognitive functions become impaired. Symptoms include "confusion, clumsiness, slurred speech, fainting/unconsciousness, hot dry skin, profuse sweating, seizures."

**Heat Exhaustion** - Often precedes heat stroke with core temperatures around 38-39C (100.4-102.2F). Symptoms include headache, nausea, dizziness, weakness, thirst, and heavy sweating.

**Heat Cramps** - Muscle spasms from depleted salt and water, typically affecting arms, legs, or torso used during work.

**Heat Syncope** - Light-headedness, dizziness, and fainting after prolonged standing or sudden position changes, often linked to dehydration.

**Heat Rash** - Skin irritation from excessive sweating causing itchy red clusters on neck, chest, groin, armpits, and creases.

**Rhabdomyolysis** - Muscle fiber breakdown releasing electrolytes into bloodstream, potentially causing kidney damage and death. Symptoms include "muscle cramps, muscle pain, dark urine, weakness, inability or decreased ability to perform physical exercise."

## III. Heat-Related Illness Prevention Program

### Program Components

An effective prevention program incorporates management commitment and aligns with OSHA's Recommended Practices for Safety and Health Programs. The program should establish procedures for determining when workers face heat hazards based on environmental conditions, clothing, and workload.

### Engineering Controls

Controls reducing heat stress include:
- Air conditioning and increased ventilation
- Cooling fans and local exhaust ventilation
- Reflective shields blocking radiant heat
- Insulation of hot surfaces
- Outdoor shade provisions

### Administrative Controls

Strategies to prevent core temperature elevation:
- Worker acclimatization beginning on day one
- Re-acclimatization after extended absences
- Scheduling work during cooler periods
- Work/rest schedules
- Limiting strenuous activities
- Relief worker rotation

### Personal Protective Equipment

Supplemental protection includes fire proximity suits, water-cooled or air-cooled garments, cooling vests, light-colored clothing, and sunscreen.

### Acclimatization Program

A structured program helps workers adapt to heat over 7-14 days of gradually increased exposure. Acclimatized workers absent for a week need 2-3 days re-acclimatization.

### Medical Monitoring Program

Robust programs include preplacement and periodic medical evaluations with on-the-job monitoring of core temperature, hydration, pulse, and blood pressure.

### Training Program

Training should address recognizing illness symptoms, proper hydration ("drinking 1 cup [8 oz.] of water or other fluids every 15-20 minutes"), heat-protective clothing use, factors affecting heat tolerance, acclimatization procedures, symptom reporting, working in pairs, and first aid. Supervisors should understand weather monitoring and adjusted temperature metrics like WBGT.

### Heat Alert Program

Programs activate when heat waves occur, defined as "abnormally and uncomfortably hot and unusually humid weather typically lasting two or more days" or when daily maximum temperature exceeds 35C (95F).

## IV. Heat Hazard Assessment

### WBGT (Wet Bulb Globe Temperature)

WBGT represents the most accurate adjustment of temperature accounting for humidity, air movement, radiant heat, and temperature. Measurements should occur hourly during the hottest portions of shifts and months, or when heat waves occur.

#### WBGT Meter Sensors

**Dry-bulb thermometer:** Measures temperature without external factor influence.

**Natural wet-bulb thermometer:** Measures sweat evaporation effectiveness, increasing with wind speed and decreasing with atmospheric moisture.

**Black globe thermometer:** Hollow copper sphere with matte black finish measuring radiant energy from sunlight or machinery.

#### WBGT Equations

**Outdoor environments (with solar radiation):**
WBGT_out = 0.7 * T_nwb + 0.2 * T_g + 0.1 * T_db

**Indoor environments (without solar radiation):**
WBGT_in = 0.7 * T_nwb + 0.3 * T_g

Where:
- T_nwb = natural wet-bulb temperature
- T_g = globe temperature
- T_db = dry-bulb temperature

#### Averaging WBGT

For continuous all-day exposures, use 60-minute average WBGT. For intermittent exposures, use 60-120 minute averages depending on exposure duration.

### Post-Incident WBGT Measurement

When measuring WBGT after heat-related incidents:
- Measure at same time of day and worker locations
- Account for weather differences between incident day and measurement day
- Compare to available incident-day WBGT data when possible

### Calculating WBGT Using Weather Data

The Argonne National Laboratory (ANL) WBGT Calculator uses algorithmic equations with internet weather data when site meters unavailable. Required inputs include:
- Air temperature
- Solar irradiance
- Wind speed
- Relative humidity
- Date and time
- Barometric pressure
- Longitude and latitude

#### Estimated Solar Irradiance by Cloud Cover

| Cloud Cover | Irradiance (W/m2) |
|---|---|
| Sunny | 990 |
| Mostly Sunny/Partly Cloudy/Scattered Clouds | 980 |
| Mostly Cloudy | 710 |
| Cloudy | 250 |

### Weather Data Sources

- National Climatic Data Center (NCDC) Climate Data Online
- National Weather Service archived 5-minute data
- Recent hourly data for past 72 hours
- Weather Underground and similar public observation sites

### Heat Index as Alternative Screening Tool

Heat index uses temperature and relative humidity to calculate adjusted values, though WBGT remains more accurate for hazard determination as it incorporates four factors rather than two.

## V. Example Problem Analysis

A real incident from Toledo, Ohio (June 8, 2002, 4 PM) involved a 30-year-old landscaper mowing assistant who collapsed and died of heat stroke. The worker was wearing two pairs of work pants, complained of light-headedness and shortness of breath two hours before collapse, was on medication with heat exposure warnings, and was pronounced dead with internal temperature of 42C (107.6F).

### Given Data
- Air Temperature: 77F (25C)
- Cloud Cover: Clear
- Wind Speed: 4.6 mph
- Relative Humidity: 56%
- Time: 2 PM (symptom onset)
- Barometric Pressure: 30.13 in Hg
- Estimated Solar Irradiance: 990 W/m2 (clear/sunny)

Analysis using ANL WBGT Calculator and historical weather data would determine whether a heat hazard existed at time of symptom onset.

## VI. References

Key sources cited include:

- ACGIH. "Heat Stress and Strain: TLV Physical Agents 7th Edition Documentation (2017)"
- Argonne National Laboratory. "Wet Bulb Globe Temperature (WBGT) Version 1.2"
- NIOSH. "Criteria for a Recommended Standard: Occupational Exposure to Heat and Hot Environments" (Publication 2016-106)
- OSHA. "Recommended Practices for Safety and Health Programs"

## VII. Appendix A: Software License

The ANL WBGT Utility is distributed under an open source license requiring attribution to "UChicago Argonne, LLC under Contract No. DE-AC02-06CH11357 with the Department of Energy." The software is provided "AS IS" without warranty of any kind.
