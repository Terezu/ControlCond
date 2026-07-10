"""Compatibilidade: os cálculos agora estão em calculos.services."""

from .services import calcular_consumo_gas, calcular_gas, calcular_valor_gas

__all__ = ["calcular_consumo_gas", "calcular_gas", "calcular_valor_gas"]
