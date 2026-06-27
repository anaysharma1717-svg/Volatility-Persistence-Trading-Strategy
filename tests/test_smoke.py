def test_smoke_imports():
	import config.settings  # noqa: F401
	import data.loader  # noqa: F401
	import indicators.atr  # noqa: F401
	import signals.raw_signal  # noqa: F401
	import backtest.engine  # noqa: F401
	import reports.summaries  # noqa: F401
