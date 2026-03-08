
# Streamlit Schenkingscalculator
# Start met: python -m streamlit run schenkingscalculator_streamlit.py

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Schenkingscalculator", layout="wide")
st.title("Schenkingscalculator Familie BV")

st.sidebar.header("Instellingen")

bv_value = st.sidebar.number_input(
    "BV waarde",
    min_value=0.0,
    value=3_000_000.0,
    step=10_000.0,
    format="%.2f"
)

years = st.sidebar.slider("Aantal jaren", 1, 20, 10)

growth = st.sidebar.slider(
    "Jaarlijks rendement BV",
    0.0,
    0.15,
    0.05,
    0.005
)

shares_total = st.sidebar.number_input(
    "Totaal aantal aandelen",
    min_value=1,
    value=180,
    step=1
)

acquisition_value_total = st.sidebar.number_input(
    "Totale verkrijgingsprijs aandelen",
    min_value=0.0,
    value=180.0,
    step=1.0,
    format="%.2f"
)

gift_pct_year_1 = st.sidebar.number_input(
    "Percentage aandelen schenking jaar 1",
    min_value=0.0,
    max_value=100.0,
    value=5.0,
    step=0.5,
    format="%.2f"
)

gift_pct_from_year_2 = st.sidebar.number_input(
    "Percentage aandelen schenking vanaf jaar 2",
    min_value=0.0,
    max_value=100.0,
    value=5.0,
    step=0.5,
    format="%.2f"
)

# Belastingparameters
box2_low = 0.245
box2_high = 0.31
box2_threshold = 67_000.0

gift_low = 0.10
gift_high = 0.20
gift_threshold = 158_669.0


def euro_fmt(x: float) -> str:
    s = f"€ {x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct_fmt(x: float) -> str:
    return f"{x*100:.2f}%".replace(".", ",")


def gift_tax(x: float) -> float:
    return min(x, gift_threshold) * gift_low + max(0.0, x - gift_threshold) * gift_high


def box2_tax(x: float) -> float:
    return min(x, box2_threshold) * box2_low + max(0.0, x - box2_threshold) * box2_high


def gross_dividend_needed_for_net(net_needed: float) -> float:
    """
    Bruto dividend op aandeelhoudersniveau zó dat netto precies 'net_needed' overblijft.
    Dus:
        bruto dividend - box2(bruto dividend) = net_needed
    """
    net_needed = max(0.0, net_needed)

    if net_needed == 0:
        return 0.0

    net_low_cap = box2_threshold * (1.0 - box2_low)

    if net_needed <= net_low_cap:
        return net_needed / (1.0 - box2_low)

    return box2_threshold + ((net_needed - net_low_cap) / (1.0 - box2_high))


with st.expander("Uitleg aannames en berekeningen", expanded=True):
    st.markdown(f"""
**Uitgangswaardes**

- Startwaarde BV: **{euro_fmt(float(bv_value))}**
- Totaal aantal aandelen: **{int(shares_total)}**
- Totale verkrijgingsprijs aandelen: **{euro_fmt(float(acquisition_value_total))}**
- Box 2 laag tarief: **{box2_low * 100:.1f}%** tot **{euro_fmt(box2_threshold)}**
- Box 2 hoog tarief: **{box2_high * 100:.1f}%** boven **{euro_fmt(box2_threshold)}**
- Schenkbelasting laag tarief: **{gift_low * 100:.1f}%** tot **{euro_fmt(gift_threshold)}**
- Schenkbelasting hoog tarief: **{gift_high * 100:.1f}%** boven **{euro_fmt(gift_threshold)}**
- Uitgangspunt: **dividend wordt eerst uitgekeerd, daarna pas geschonken**

**Berekening dividendbedrag**

1. Eerst berekenen we de **AB-grondslag** van de schenking.  
2. Daarover berekenen we de **box 2 over schenking**.  
3. Daarna rekenen we terug welk **bruto dividend voor Jeroen** nodig is zodat na box 2 op dat dividend
   netto precies genoeg overblijft om die box 2 over de schenking te betalen.

Dus:

- **bruto dividend Jeroen - box 2 over dividend Jeroen = box 2 over schenking**

Omdat het dividend **voor de schenking** wordt uitgekeerd, wordt het totale dividend in de BV verdeeld volgens de
aandelenverhouding aan het **begin van het jaar**:
- Jeroen ontvangt: **Jeroen % × totaal dividend**
- kind ontvangt: **kind % × totaal dividend**

Daarom is het **totale dividend uit de BV** vaak hoger dan het dividend dat Jeroen persoonlijk ontvangt.

**Berekening AB-grondslag**

De AB-grondslag wordt berekend als:

**waarde geschonken aandelen na dividend - verkrijgingsprijs van datzelfde deel**

Dus:
- eerst gaat het dividend uit de BV
- daarna is de waarde van de BV lager
- vervolgens wordt de waarde van de schenking berekend op basis van die **lagere BV-waarde**

**Berekening schenkbelasting**

De schenkbelasting wordt berekend over de waarde van de geschonken aandelen **na dividend**:
- **{gift_low * 100:.1f}%** over de eerste **{euro_fmt(gift_threshold)}**
- **{gift_high * 100:.1f}%** over het meerdere
""")


def simulate():
    bv = float(bv_value)
    father_pct = 1.0
    child_pct = 0.0
    father_acquisition_remaining = float(acquisition_value_total)

    rows = []

    for y in range(1, years + 1):
        father_pct_start = father_pct
        child_pct_start = child_pct
        bv_begin = bv

        pct_input = float(gift_pct_year_1) if y == 1 else float(gift_pct_from_year_2)
        pct_company = min(max(pct_input / 100.0, 0.0), father_pct_start)

        # Omdat dividend vóór schenking plaatsvindt, moet het benodigde dividend
        # worden bepaald met het belang van Jeroen aan het begin van het jaar.
        # Eerst benaderen we de latere schenking op basis van BV-waarde ná dividend.
        # Daarvoor lossen we iteratief op:
        # 1) bereken gift value op basis van bv na dividend
        # 2) bereken box2 over schenking
        # 3) bepaal netto dividend dat Jeroen nodig heeft
        # 4) vertaal dat naar totaal dividend uit de BV, rekening houdend met zijn % belang
        total_dividend = 0.0
        dividend_jeroen = 0.0
        dividend_kind = 0.0
        ab_groundslag = 0.0
        gift_val = 0.0
        acquisition_part = 0.0
        box2_due_on_gift = 0.0
        box2_on_dividend_jeroen = 0.0
        box2_on_dividend_kind = 0.0

        if father_pct_start > 0 and pct_company > 0:
            for _ in range(40):
                bv_after_dividend = max(0.0, bv_begin - total_dividend)

                gift_val = pct_company * bv_after_dividend

                acquisition_part = (
                    (pct_company / father_pct_start) * father_acquisition_remaining
                    if father_pct_start > 0 else 0.0
                )

                ab_groundslag = max(0.0, gift_val - acquisition_part)
                box2_due_on_gift = box2_tax(ab_groundslag)

                # Jeroen moet netto dit bedrag overhouden uit zijn eigen dividend
                dividend_jeroen_new = gross_dividend_needed_for_net(box2_due_on_gift)

                # Totaal dividend uit de BV moet hoger zijn als Jeroen minder dan 100% bezit
                total_dividend_new = (
                    dividend_jeroen_new / father_pct_start
                    if father_pct_start > 0 else 0.0
                )

                if abs(total_dividend_new - total_dividend) < 0.01:
                    total_dividend = total_dividend_new
                    dividend_jeroen = dividend_jeroen_new
                    break

                total_dividend = total_dividend_new
                dividend_jeroen = dividend_jeroen_new

            dividend_kind = total_dividend * child_pct_start
            box2_on_dividend_jeroen = box2_tax(dividend_jeroen)
            box2_on_dividend_kind = box2_tax(dividend_kind)
        else:
            bv_after_dividend = bv_begin
            gift_val = 0.0
            acquisition_part = 0.0
            ab_groundslag = 0.0
            box2_due_on_gift = 0.0
            total_dividend = 0.0
            dividend_jeroen = 0.0
            dividend_kind = 0.0
            box2_on_dividend_jeroen = 0.0
            box2_on_dividend_kind = 0.0

        bv_after_dividend = max(0.0, bv_begin - total_dividend)

        # Schenkbelasting wordt berekend over waarde schenking na dividend
        gift_t = gift_tax(gift_val)

        father_pct = max(0.0, father_pct_start - pct_company)
        child_pct = min(1.0, child_pct_start + pct_company)
        father_acquisition_remaining = max(0.0, father_acquisition_remaining - acquisition_part)

        bv_end = bv_after_dividend * (1.0 + growth)

        rows.append({
            "jaar": y,
            "BV waarde begin jaar": bv_begin,
            "percentage schenking": pct_company,
            "Jeroen % begin jaar": father_pct_start,
            "kind % begin jaar": child_pct_start,
            "totaal dividend BV": total_dividend,
            "dividend Jeroen": dividend_jeroen,
            "dividend kind": dividend_kind,
            "AB grondslag": ab_groundslag,
            "waarde schenking na dividend": gift_val,
            "box 2 over schenking": box2_due_on_gift,
            "box 2 over dividend Jeroen": box2_on_dividend_jeroen,
            "box 2 over dividend kind": box2_on_dividend_kind,
            "schenkbelasting": gift_t,
            "belang kind einde jaar": child_pct,
            "BV waarde einde jaar": bv_end
        })

        bv = bv_end

    return pd.DataFrame(rows)


df = simulate()

st.subheader("Resultaten")

display_df = df.copy()

currency_cols = [
    "BV waarde begin jaar",
    "totaal dividend BV",
    "dividend Jeroen",
    "dividend kind",
    "AB grondslag",
    "waarde schenking na dividend",
    "box 2 over schenking",
    "box 2 over dividend Jeroen",
    "box 2 over dividend kind",
    "schenkbelasting",
    "BV waarde einde jaar"
]

for col in currency_cols:
    display_df[col] = display_df[col].map(euro_fmt)

pct_cols = [
    "percentage schenking",
    "Jeroen % begin jaar",
    "kind % begin jaar",
    "belang kind einde jaar"
]
for col in pct_cols:
    display_df[col] = display_df[col].map(pct_fmt)

st.dataframe(display_df, use_container_width=True)

fig = plt.figure(figsize=(8, 4.5))
plt.plot(df["jaar"], df["belang kind einde jaar"] * 100, marker="o")
plt.xlabel("Jaar")
plt.ylabel("Belang kind (%)")
plt.title("Cumulatief belang kind")
plt.tight_layout()
st.pyplot(fig)

fig2 = plt.figure(figsize=(8, 4.5))
plt.plot(df["jaar"], df["box 2 over schenking"], marker="o", label="Box 2 over schenking")
plt.plot(df["jaar"], df["box 2 over dividend Jeroen"], marker="o", label="Box 2 over dividend Jeroen")
plt.plot(df["jaar"], df["box 2 over dividend kind"], marker="o", label="Box 2 over dividend kind")
plt.plot(df["jaar"], df["schenkbelasting"], marker="o", label="Schenkbelasting")
plt.legend()
plt.xlabel("Jaar")
plt.ylabel("Bedrag (€)")
plt.title("Belastingen per jaar")
plt.tight_layout()
st.pyplot(fig2)

st.download_button(
    "Download resultaten CSV",
    df.to_csv(index=False),
    "resultaten_schenking.csv",
    "text/csv"
)
