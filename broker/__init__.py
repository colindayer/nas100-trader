"""Broker intelligence layer.

Strategies consume BrokerProfile; they do not query MT5 directly. The broker is part of the
experimental environment, and two brokers are not the same environment -- FTMO offers 166
symbols and no bonds; Pepperstone offers 1729 including 7 bonds. A hypothesis that cannot be
evaluated on one broker is NOT thereby false.
"""
from broker.profile import BrokerProfile, SymbolSpec
from broker.classify import classify, AssetClass
from broker.financing import swap_usd_per_lot_night, financing_drag

__all__ = ["BrokerProfile", "SymbolSpec", "classify", "AssetClass",
           "swap_usd_per_lot_night", "financing_drag"]
