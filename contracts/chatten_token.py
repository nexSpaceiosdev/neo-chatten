"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     CHATTEN COMPUTE-FI PROTOCOL                              ║
║                     NEP-11 Divisible + Marketplace                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

A Hyperledger-style Compute Finance Protocol on Neo N3.
Compiler: neo3-boa v1.4.x
"""

from typing import Any, cast

# =============================================================================
# NEO3-BOA v1.4.x IMPORTS
# =============================================================================

from boa3.sc.compiletime import public  # type: ignore
from boa3.sc.utils import Nep11TransferEvent, call_contract, Iterator  # type: ignore
from boa3.sc.runtime import check_witness, calling_script_hash, executing_script_hash, script_container  # type: ignore
from boa3.sc.types import UInt160, Transaction  # type: ignore
from boa3.sc.storage import get, put, delete, find, get_int, put_int  # type: ignore
from boa3.sc.contracts import GasToken, CryptoLib, ContractManagement  # type: ignore


# =============================================================================
# STORAGE PREFIXES
# =============================================================================

PREFIX_BALANCE = b'\x01'
PREFIX_SUPPLY = b'\x02'
PREFIX_TOTAL_SUPPLY = b'\x03'
PREFIX_ADMIN = b'\x10'
PREFIX_PAUSED = b'\x11'
PREFIX_ORACLE = b'\x12'
PREFIX_MINTER = b'\x13'
PREFIX_PRICE = b'\x20'
PREFIX_GAS_RESERVE = b'\x21'


# =============================================================================
# CONSTANTS
# =============================================================================

TOKEN_SYMBOL: str = "COMPUTE"
TOKEN_DECIMALS: int = 8
ONE_TOKEN: int = 100_000_000
ZERO_ADDRESS: bytes = b'\x00' * 20
GAS_HASH: bytes = b'\xcf\x76\xe2\x8b\xd0\x06\x2c\x4a\x47\x8e\xe3\x55\x61\x01\x13\x19\xf3\xcf\xa4\xd2'


# =============================================================================
# EVENTS
# =============================================================================

on_transfer = Nep11TransferEvent


# =============================================================================
# DEPLOYMENT
# =============================================================================

@public
def _deploy(data: Any, update: bool) -> None:
    if not update:
        tx = cast(Transaction, script_container)
        deployer = tx.sender
        put(PREFIX_ADMIN, deployer)
        put_int(PREFIX_PAUSED, 0)
        put_int(PREFIX_TOTAL_SUPPLY, 0)
        put_int(PREFIX_GAS_RESERVE, 0)
        put_int(PREFIX_ORACLE + deployer, 1)
        put_int(PREFIX_MINTER + deployer, 1)


# =============================================================================
# NEP-11 STANDARD
# =============================================================================

@public(safe=True)
def symbol() -> str:
    return TOKEN_SYMBOL


@public(safe=True)
def decimals() -> int:
    return TOKEN_DECIMALS


@public(safe=True)
def totalSupply() -> int:
    return get_int(PREFIX_TOTAL_SUPPLY)


@public(safe=True)
def balanceOf(owner: UInt160) -> int:
    assert len(owner) == 20, "Invalid"
    return get_int(PREFIX_BALANCE + owner)


@public(safe=True)
def tokenSupply(token_id: bytes) -> int:
    return get_int(PREFIX_SUPPLY + token_id)


@public(safe=True)
def tokensOf(owner: UInt160) -> Iterator:
    assert len(owner) == 20, "Invalid"
    return find(PREFIX_BALANCE + owner)


# =============================================================================
# PRICING
# =============================================================================

@public(safe=True)
def get_current_price(model_id: bytes) -> int:
    """Get spot price for model in GAS units. Safe method."""
    assert len(model_id) > 0, "Invalid"
    token_id = CryptoLib.sha256(model_id)
    return get_int(PREFIX_PRICE + token_id)


@public
def update_price_oracle(model_id: bytes, price_gas: int) -> bool:
    """Update price. Oracle only."""
    assert _not_paused(), "Paused"
    assert len(model_id) > 0, "Invalid"
    assert price_gas > 0, "Invalid"
    assert _is_oracle(calling_script_hash), "Not oracle"
    
    token_id = CryptoLib.sha256(model_id)
    put_int(PREFIX_PRICE + token_id, price_gas)
    return True


@public(safe=True)
def get_gas_reserve() -> int:
    return get_int(PREFIX_GAS_RESERVE)


# =============================================================================
# TRANSFER
# =============================================================================

@public
def transfer(from_addr: UInt160, to: UInt160, amount: int, token_id: bytes, data: Any) -> bool:
    assert len(from_addr) == 20 and len(to) == 20, "Invalid"
    assert amount > 0, "Invalid"
    assert _not_paused(), "Paused"
    assert check_witness(from_addr), "Not authorized"
    
    from_key = PREFIX_BALANCE + from_addr + token_id
    from_bal = get_int(from_key)
    if from_bal < amount:
        return False
    
    new_from = from_bal - amount
    if new_from > 0:
        put_int(from_key, new_from)
    else:
        delete(from_key)
    
    to_key = PREFIX_BALANCE + to + token_id
    to_bal = get_int(to_key)
    put_int(to_key, to_bal + amount)
    
    on_transfer(from_addr, to, amount, token_id)
    
    contract = ContractManagement.get_contract(to)
    if contract is not None:
        call_contract(to, 'onNEP11Payment', [from_addr, amount, token_id, data])
    
    return True


# =============================================================================
# MINTING
# =============================================================================

@public
def mint(to: UInt160, model_id: bytes, amount: int, quality: int) -> bool:
    assert _not_paused(), "Paused"
    assert len(to) == 20, "Invalid"
    assert len(model_id) > 0, "Invalid"
    assert amount > 0, "Invalid"
    assert quality >= 50 and quality <= 100, "Invalid quality"
    assert _is_minter(calling_script_hash), "Not minter"
    
    token_id = CryptoLib.sha256(model_id)
    actual = amount * quality // 100
    assert actual > 0, "Too small"
    
    # Balance
    key = PREFIX_BALANCE + to + token_id
    bal = get_int(key)
    put_int(key, bal + actual)
    
    # Token supply
    sup_key = PREFIX_SUPPLY + token_id
    sup = get_int(sup_key)
    put_int(sup_key, sup + actual)
    
    # Total
    tot = get_int(PREFIX_TOTAL_SUPPLY)
    put_int(PREFIX_TOTAL_SUPPLY, tot + actual)
    
    on_transfer(UInt160(ZERO_ADDRESS), to, actual, token_id)
    return True


@public
def burn(owner: UInt160, token_id: bytes, amount: int) -> bool:
    assert _not_paused(), "Paused"
    assert check_witness(owner), "Not authorized"
    assert amount > 0, "Invalid"
    
    key = PREFIX_BALANCE + owner + token_id
    current = get_int(key)
    if current < amount:
        return False
    
    new_bal = current - amount
    if new_bal > 0:
        put_int(key, new_bal)
    else:
        delete(key)
    
    sup_key = PREFIX_SUPPLY + token_id
    sup = get_int(sup_key)
    put_int(sup_key, sup - amount)
    
    tot = get_int(PREFIX_TOTAL_SUPPLY)
    put_int(PREFIX_TOTAL_SUPPLY, tot - amount)
    
    on_transfer(owner, UInt160(ZERO_ADDRESS), amount, token_id)
    return True


# =============================================================================
# SWAP
# =============================================================================

@public
def buy_compute(buyer: UInt160, model_id: bytes, gas_amount: int) -> int:
    assert _not_paused(), "Paused"
    assert len(buyer) == 20, "Invalid"
    assert len(model_id) > 0, "Invalid"
    assert gas_amount > 1000, "Too small"
    
    token_id = CryptoLib.sha256(model_id)
    price = get_int(PREFIX_PRICE + token_id)
    assert price > 0, "No price"
    
    fee = gas_amount * 3 // 1000
    net = gas_amount - fee
    compute = net * ONE_TOKEN // price
    assert compute > 0, "Too small"
    
    # Mint
    key = PREFIX_BALANCE + buyer + token_id
    bal = get_int(key)
    put_int(key, bal + compute)
    
    sup_key = PREFIX_SUPPLY + token_id
    sup = get_int(sup_key)
    put_int(sup_key, sup + compute)
    
    tot = get_int(PREFIX_TOTAL_SUPPLY)
    put_int(PREFIX_TOTAL_SUPPLY, tot + compute)
    
    # Reserve
    res = get_int(PREFIX_GAS_RESERVE)
    put_int(PREFIX_GAS_RESERVE, res + gas_amount)
    
    on_transfer(UInt160(ZERO_ADDRESS), buyer, compute, token_id)
    return compute


@public
def sell_compute(seller: UInt160, model_id: bytes, amount: int) -> int:
    assert _not_paused(), "Paused"
    assert check_witness(seller), "Not authorized"
    assert len(model_id) > 0, "Invalid"
    assert amount > 1000, "Too small"
    
    token_id = CryptoLib.sha256(model_id)
    
    key = PREFIX_BALANCE + seller + token_id
    current = get_int(key)
    assert current >= amount, "Insufficient"
    
    price = get_int(PREFIX_PRICE + token_id)
    assert price > 0, "No price"
    
    gross = amount * price // ONE_TOKEN
    fee = gross * 3 // 1000
    net = gross - fee
    assert net > 0, "Too small"
    
    reserve = get_int(PREFIX_GAS_RESERVE)
    assert reserve >= net, "Insufficient reserve"
    
    # Burn
    new_bal = current - amount
    if new_bal > 0:
        put_int(key, new_bal)
    else:
        delete(key)
    
    sup_key = PREFIX_SUPPLY + token_id
    sup = get_int(sup_key)
    put_int(sup_key, sup - amount)
    
    tot = get_int(PREFIX_TOTAL_SUPPLY)
    put_int(PREFIX_TOTAL_SUPPLY, tot - amount)
    
    put_int(PREFIX_GAS_RESERVE, reserve - net)
    
    ok = GasToken.transfer(executing_script_hash, seller, net, None)
    assert ok, "Transfer failed"
    
    on_transfer(seller, UInt160(ZERO_ADDRESS), amount, token_id)
    return net


# =============================================================================
# NEP-17 RECEIVER
# =============================================================================

@public
def onNEP17Payment(from_addr: UInt160, amount: int, data: Any) -> None:
    assert calling_script_hash == UInt160(GAS_HASH), "Only GAS"
    res = get_int(PREFIX_GAS_RESERVE)
    put_int(PREFIX_GAS_RESERVE, res + amount)


@public
def onNEP11Payment(from_addr: UInt160, amount: int, token_id: bytes, data: Any) -> None:
    pass


# =============================================================================
# ADMIN
# =============================================================================

@public
def pause() -> bool:
    assert _is_admin(calling_script_hash), "Not admin"
    put_int(PREFIX_PAUSED, 1)
    return True


@public
def resume() -> bool:
    assert _is_admin(calling_script_hash), "Not admin"
    put_int(PREFIX_PAUSED, 0)
    return True


@public(safe=True)
def isPaused() -> bool:
    return not _not_paused()


@public
def set_oracle(addr: UInt160, auth: bool) -> bool:
    assert _is_admin(calling_script_hash), "Not admin"
    if auth:
        put_int(PREFIX_ORACLE + addr, 1)
    else:
        delete(PREFIX_ORACLE + addr)
    return True


@public
def set_minter(addr: UInt160, auth: bool) -> bool:
    assert _is_admin(calling_script_hash), "Not admin"
    if auth:
        put_int(PREFIX_MINTER + addr, 1)
    else:
        delete(PREFIX_MINTER + addr)
    return True


@public(safe=True)
def get_admin() -> UInt160:
    data = get(PREFIX_ADMIN)
    if len(data) == 0:
        return UInt160(ZERO_ADDRESS)
    return UInt160(data)


@public(safe=True)
def is_oracle(addr: UInt160) -> bool:
    return _is_oracle(addr)


@public(safe=True)
def is_minter(addr: UInt160) -> bool:
    return _is_minter(addr)


@public
def withdraw_gas(to: UInt160, amount: int) -> bool:
    assert _is_admin(calling_script_hash), "Not admin"
    assert len(to) == 20, "Invalid"
    assert amount > 0, "Invalid"
    
    reserve = get_int(PREFIX_GAS_RESERVE)
    assert reserve >= amount, "Insufficient"
    
    put_int(PREFIX_GAS_RESERVE, reserve - amount)
    ok = GasToken.transfer(executing_script_hash, to, amount, None)
    assert ok, "Failed"
    return True


# =============================================================================
# INTERNAL
# =============================================================================

def _not_paused() -> bool:
    return get_int(PREFIX_PAUSED) == 0


def _is_admin(addr: UInt160) -> bool:
    return get(PREFIX_ADMIN) == addr


def _is_oracle(addr: UInt160) -> bool:
    return get_int(PREFIX_ORACLE + addr) == 1


def _is_minter(addr: UInt160) -> bool:
    return get_int(PREFIX_MINTER + addr) == 1
