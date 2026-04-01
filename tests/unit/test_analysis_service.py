from app.services.analysis_service import AnalysisService


def test_pre_analyze_flags_high_risk_conditions():
    service = AnalysisService()
    result = service.pre_analyze(
        {
            "breathing_rate": 30,
            "snore_level": 80,
            "temperature": 31,
            "humidity": 75,
        }
    )
    assert result["risk_level"] == "high"
    assert "high_snore" in result["flags"]
