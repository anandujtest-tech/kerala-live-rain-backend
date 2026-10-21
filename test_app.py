from main import safe_rain, records, find, DISTRICTS
assert len(DISTRICTS)==14
assert safe_rain(None) is None
assert safe_rain("null") is None
assert safe_rain("-1") is None
assert safe_rain("NaN") is None
assert safe_rain("12.43")==12.43
assert records({"data":[{"District":"Kottayam"}]})==[{"District":"Kottayam"}]
assert find({"Daily Actual":"3.2"},"DailyActual")=="3.2"
print("Backend normalization tests passed")
