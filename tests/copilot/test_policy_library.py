"""Policy library: legislation XML becomes numbered passages, keyword search ranks the right one first."""

from copilot.policy_library import BM25, Library, Passage, expand, parse_legislation

XML = """<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
<Metadata><valid>2026-01-01</valid></Metadata>
<Secondary><Body><P1group><Title>Limits on the use of payment instruments</Title><P1>
<P2><Pnumber>1</Pnumber><P2para><Text>A framework contract may provide for the provider to stop the use of a
payment instrument on reasonable grounds relating to—</Text>
<P3><Pnumber>a</Pnumber><P3para><Text>the security of the payment instrument;</Text></P3para></P3></P2para></P2>
<P2><Pnumber>2</Pnumber><P2para><Text>The provider must allow the use of the payment instrument as soon as
practicable after the reasons cease to exist.</Text><Commentaries><Commentary>editorial note</Commentary>
</Commentaries></P2para></P2>
</P1></P1group></Body></Secondary></Legislation>"""


def test_parse_legislation_splits_paragraphs_and_skips_commentary(tmp_path):
    f = tmp_path / "psrs_reg71.xml"
    f.write_text(XML)
    ps = parse_legislation(f, "PSRs 2017", "reg", "https://example/")
    assert [p.id for p in ps] == ["PSRs 2017 reg 71(1)", "PSRs 2017 reg 71(2)"]
    assert "(a) the security" in ps[0].text
    assert "editorial note" not in ps[1].text
    assert ps[0].heading == "Limits on the use of payment instruments" and ps[0].version_date == "2026-01-01"


def test_glossary_adds_legal_wording():
    assert "stop the use of the payment instrument" in expand("When may the bank block a card?")
    assert "allow the use" in expand("When must the bank unblock the card?")
    assert expand("weather today") == "weather today"


def test_keyword_search_finds_the_matching_passage():
    passages = [Passage(f"P{i}", "S", "x", "", t, "", "", "", "") for i, t in enumerate([
        "refund the amount no later than the end of the business day following",
        "the payer is liable up to a maximum of £35 for losses from a lost or stolen instrument",
        "notify without undue delay and no later than 13 months after the debit date"])]
    lib = Library(passages, vectors=None)
    assert lib.search("most a customer pays for a stolen card £35", k=1)[0][0].id == "P1"
    assert BM25([p.text for p in passages]).scores("13 months")[2] > 0
