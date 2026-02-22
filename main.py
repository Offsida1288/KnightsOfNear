# KnightsOfNear_engine.py
# Round-table access ledger and KOK NFT registry. Forged at the boundary of NEAR and EVM.
# Use at your own risk. Not audited.

from __future__ import annotations

import hashlib
import json
import secrets
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

# ---------------------------------------------------------------------------
# Deployed roles (EVM mainnet–style; do not reuse elsewhere)
# ---------------------------------------------------------------------------

GOVERNANCE_ROUND = "0xe7f2a4c9b1d8e3f6a0c5b2d9e4f7a1c6b3d0e8f1"
TABLE_TREASURY = "0x9a3d6f1c8e4b7a0d2f5e8c1b4a7d0e3f6c9b2a5d8"
SEAT_REGISTRAR = "0x1b5e9c3a7d0f4e8b2c6a9d3f7b0e5c1a8d4f2e6b0"
KOK_VAULT = "0x4c8a2f6e0b9d3a7c1e5f8b2d6a0c4e9f3b7d1a8c2"
BRIDGE_RELAY = "0xd2f7a1e6c0b9d4e8a3f5c1b7d0e4a9f2c6b3d5e1"
ROUND_TABLE_CORE = "0x6b0e4a8d2f7c1b5e9a3d6f0c4b8e2a7d1f5c9b0a4"
KON_TOKEN_HUB = "0xa8d1f5c9e3b7a0d4e8c2f6b9a1d5e0c3f7a4b8d2e"
MERLIN_GATE = "0x3f7b2e6a9d1c5f0e8b4a7d2f6c9e1b5a0d3f8c2b6"
LANCELOT_GATE = "0x0e5a9d3f7c2b6e1a4d8f0c5b9e3a7d2f6c1b4e0a8"
GAWAIN_GATE = "0xb9e2c6a0d4f8b1e5c9a3d7f2b6e0c4a8d1f5b3c7"
DEFAULT_FEE_RECIPIENT = "0x7c4d0f3a8e2b6c9d1f5a0e4b8c2d7f3a6e1b9c5d0"
BURN_ADDRESS = "0x000000000000000000000000000000000000dEaD"

# ---------------------------------------------------------------------------
# Constants (EVM-aligned)
# ---------------------------------------------------------------------------

KON_DECIMALS = 18
KON_SCALE = 10**18
KON_INITIAL_SUPPLY = 1_000_000_000 * KON_SCALE
KON_MAX_SUPPLY = 2_000_000_000 * KON_SCALE
ROUND_TABLE_SEATS = 150
KOK_COLLECTION_SIZE = 16
KON_BASIS_POINTS = 10_000
KON_MAX_FEE_BASIS = 250
KON_MIN_STAKE_FOR_SEAT = 10_000 * KON_SCALE
TABLE_ENTRY_FEE_WEI = 100_000_000_000_000
MAX_CLAIM_PER_TX = 50
DOMAIN_SEPARATOR_SALT = "0x8f4a2c6e1b9d0f3a7c5e8b2d6f1a4c9e0b3d7f2"
KOK_NAMESPACE = hashlib.sha256(b"KnightsOfNear.KOK_COLLECTION").hexdigest()
ROUND_TABLE_NAMESPACE = hashlib.sha256(b"KnightsOfNear.ROUND_TABLE_ACCESS").hexdigest()
EIP712_VERSION = "1"

# ---------------------------------------------------------------------------
# Custom errors (unique to this contract)
# ---------------------------------------------------------------------------


class KnightsOfNearError(Exception):
    """Base for KnightsOfNear engine."""

    pass


class TableGuardDenied(KnightsOfNearError):
    pass


class SeatAlreadyClaimed(KnightsOfNearError):
    pass


class NotAKnight(KnightsOfNearError):
    pass


class InsufficientStake(KnightsOfNearError):
    pass


class RoundTableFull(KnightsOfNearError):
    pass


class ZeroAddress(KnightsOfNearError):
    pass


class ZeroAmount(KnightsOfNearError):
    pass


class ExceedsBalance(KnightsOfNearError):
    pass


class ExceedsAllowance(KnightsOfNearError):
    pass


class FeeBasisTooHigh(KnightsOfNearError):
    pass


class KOKIndexOutOfRange(KnightsOfNearError):
    pass


class KOKAlreadyMinted(KnightsOfNearError):
    pass


class NotKOKOwner(KnightsOfNearError):
    pass


class NotGovernance(KnightsOfNearError):
    pass


class NotRegistrar(KnightsOfNearError):
    pass


class TableNotUnlocked(KnightsOfNearError):
    pass


class ClaimBatchTooLarge(KnightsOfNearError):
    pass


class InvalidSeatId(KnightsOfNearError):
    pass


class TransferToZero(KnightsOfNearError):
    pass


class MintExceedsCap(KnightsOfNearError):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SeatStatus(Enum):
    VACANT = 0
    CLAIMED = 1
    FROZEN = 2


class KOKRarity(Enum):
    COMMON = 0
    UNCOMMON = 1
    RARE = 2
    EPIC = 3
    LEGENDARY = 4


# ---------------------------------------------------------------------------
# Events (log-style structures)
# ---------------------------------------------------------------------------


@dataclass
class EventTransfer:
    from_addr: str
    to_addr: str
    amount: int


@dataclass
class EventSeatClaimed:
    seat_id: int
    knight: str
    stake_amount: int


@dataclass
class EventKOKMinted:
    token_id: int
    to_addr: str
    rarity: KOKRarity


@dataclass
class EventTableUnlocked:
    unlocked_by: str
    block_ts: int


# ---------------------------------------------------------------------------
# Round table seat
# ---------------------------------------------------------------------------


@dataclass
class RoundTableSeat:
    seat_id: int
    occupant: str
    stake_amount: int
    claimed_at_block: int
    status: SeatStatus


# ---------------------------------------------------------------------------
# KOK NFT metadata (16 high-profile knights)
# ---------------------------------------------------------------------------

KOK_METADATA: List[Dict[str, Any]] = [
    {
        "token_id": 0,
        "name": "Arthur of Near",
        "description": "Sovereign of the Round Table. One blade to bind them.",
        "rarity": KOKRarity.LEGENDARY,
        "attributes": [{"trait_type": "Title", "value": "High King"}, {"trait_type": "Power", "value": 98}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Arthur_0").hexdigest()[:64],
    },
    {
        "token_id": 1,
        "name": "Merlin the Seer",
        "description": "Oracle of NEAR. Sees across chains.",
        "rarity": KOKRarity.LEGENDARY,
        "attributes": [{"trait_type": "Title", "value": "Prophet"}, {"trait_type": "Power", "value": 95}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Merlin_1").hexdigest()[:64],
    },
    {
        "token_id": 2,
        "name": "Lancelot the Pure",
        "description": "Champion of the realm. Unbroken in battle.",
        "rarity": KOKRarity.EPIC,
        "attributes": [{"trait_type": "Title", "value": "First Knight"}, {"trait_type": "Power", "value": 94}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Lancelot_2").hexdigest()[:64],
    },
    {
        "token_id": 3,
        "name": "Guinevere of the Gate",
        "description": "Keeper of the bridge between NEAR and EVM.",
        "rarity": KOKRarity.EPIC,
        "attributes": [{"trait_type": "Title", "value": "Bridge Keeper"}, {"trait_type": "Power", "value": 90}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Guinevere_3").hexdigest()[:64],
    },
    {
        "token_id": 4,
        "name": "Gawain the Green",
        "description": "Guardian of the green layer. Staking champion.",
        "rarity": KOKRarity.EPIC,
        "attributes": [{"trait_type": "Title", "value": "Green Knight"}, {"trait_type": "Power", "value": 88}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Gawain_4").hexdigest()[:64],
    },
    {
        "token_id": 5,
        "name": "Percival the Seeker",
        "description": "Quest for the grail across L1 and L2.",
        "rarity": KOKRarity.RARE,
        "attributes": [{"trait_type": "Title", "value": "Grail Seeker"}, {"trait_type": "Power", "value": 85}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Percival_5").hexdigest()[:64],
    },
    {
        "token_id": 6,
        "name": "Tristan the Bound",
        "description": "Bound to the chain. Loyalty immutable.",
        "rarity": KOKRarity.RARE,
        "attributes": [{"trait_type": "Title", "value": "Oathbound"}, {"trait_type": "Power", "value": 82}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Tristan_6").hexdigest()[:64],
    },
    {
        "token_id": 7,
        "name": "Galahad the Virtuous",
        "description": "Pure of heart. First to the round table.",
        "rarity": KOKRarity.RARE,
        "attributes": [{"trait_type": "Title", "value": "Virtuous"}, {"trait_type": "Power", "value": 87}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Galahad_7").hexdigest()[:64],
    },
    {
        "token_id": 8,
        "name": "Bedivere the Marshal",
        "description": "Marshal of the table. Order in chaos.",
        "rarity": KOKRarity.UNCOMMON,
        "attributes": [{"trait_type": "Title", "value": "Marshal"}, {"trait_type": "Power", "value": 78}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Bedivere_8").hexdigest()[:64],
    },
    {
        "token_id": 9,
        "name": "Kay the Seneschal",
        "description": "Keeper of the keys. Access control.",
        "rarity": KOKRarity.UNCOMMON,
        "attributes": [{"trait_type": "Title", "value": "Seneschal"}, {"trait_type": "Power", "value": 75}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Kay_9").hexdigest()[:64],
    },
    {
        "token_id": 10,
        "name": "Bors the Twin",
        "description": "Dual-chain knight. NEAR and EVM.",
        "rarity": KOKRarity.UNCOMMON,
        "attributes": [{"trait_type": "Title", "value": "Twin Knight"}, {"trait_type": "Power", "value": 76}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Bors_10").hexdigest()[:64],
    },
    {
        "token_id": 11,
        "name": "Ector the Foster",
        "description": "Raised the king. Guardian of the realm.",
        "rarity": KOKRarity.UNCOMMON,
        "attributes": [{"trait_type": "Title", "value": "Foster"}, {"trait_type": "Power", "value": 74}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Ector_11").hexdigest()[:64],
    },
    {
        "token_id": 12,
        "name": "Lamorak the Bold",
        "description": "Bold in battle. No rollback.",
        "rarity": KOKRarity.COMMON,
        "attributes": [{"trait_type": "Title", "value": "Bold"}, {"trait_type": "Power", "value": 70}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Lamorak_12").hexdigest()[:64],
    },
    {
        "token_id": 13,
        "name": "Gareth the Fair",
        "description": "Fair in governance. One vote, one knight.",
        "rarity": KOKRarity.COMMON,
        "attributes": [{"trait_type": "Title", "value": "Fair"}, {"trait_type": "Power", "value": 68}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Gareth_13").hexdigest()[:64],
    },
    {
        "token_id": 14,
        "name": "Agravain the Sharp",
        "description": "Sharp wit. Smart contract reviewer.",
        "rarity": KOKRarity.COMMON,
        "attributes": [{"trait_type": "Title", "value": "Sharp"}, {"trait_type": "Power", "value": 65}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Agravain_14").hexdigest()[:64],
    },
    {
        "token_id": 15,
        "name": "Mordred the Shadow",
        "description": "Shadow of the table. Testnet knight.",
        "rarity": KOKRarity.COMMON,
        "attributes": [{"trait_type": "Title", "value": "Shadow"}, {"trait_type": "Power", "value": 72}],
        "image_hash": "0x" + hashlib.sha256(b"KOK_Mordred_15").hexdigest()[:64],
    },
]


def _normalize_addr(addr: str) -> str:
    a = addr.strip()
    if a.startswith("0x"):
        a = a[2:]
    return "0x" + a.lower().zfill(40)[-40:]


def _require(cond: bool, exc: type[KnightsOfNearError]) -> None:
    if not cond:
        raise exc()


# ---------------------------------------------------------------------------
# KnightsOfNear engine
# ---------------------------------------------------------------------------


class KnightsOfNearEngine:
    """
    Utility meme token and Round Table access. KOK NFT collection of 16 knights.
    EVM-safe logic: bounds checks, no overflow assumptions, standard access.
    """

    def __init__(self, genesis_block: int = 0):
        self.genesis_block = genesis_block
        self._balances: Dict[str, int] = {}
        self._allowances: Dict[Tuple[str, str], int] = {}
        self._total_supply = 0
        self._seats: Dict[int, RoundTableSeat] = {}
        self._seat_by_knight: Dict[str, int] = {}
        self._kok_owners: Dict[int, str] = {}
        self._kok_minted: Dict[int, bool] = {i: False for i in range(KOK_COLLECTION_SIZE)}
        self._table_unlocked = False
        self._unlock_block = 0
        self._transfer_fee_basis = 50
        self._fee_recipient = _normalize_addr(DEFAULT_FEE_RECIPIENT)
        self._events: List[Any] = []
        self._mint_cap_used = 0

        for sid in range(ROUND_TABLE_SEATS):
            self._seats[sid] = RoundTableSeat(
                seat_id=sid,
                occupant="",
                stake_amount=0,
                claimed_at_block=0,
                status=SeatStatus.VACANT,
            )

        self._mint(GOVERNANCE_ROUND, KON_INITIAL_SUPPLY)

    def _mint(self, to: str, amount: int) -> None:
        to = _normalize_addr(to)
        _require(to != BURN_ADDRESS and to != "0x" + "0" * 40, ZeroAddress)
        _require(amount > 0, ZeroAmount)
        new_total = self._total_supply + amount
        _require(new_total <= KON_MAX_SUPPLY, MintExceedsCap)
        self._total_supply = new_total
        self._balances[to] = self._balances.get(to, 0) + amount

    def _burn(self, from_addr: str, amount: int) -> None:
        from_addr = _normalize_addr(from_addr)
        bal = self._balances.get(from_addr, 0)
        _require(bal >= amount, ExceedsBalance)
        self._balances[from_addr] = bal - amount
        self._total_supply -= amount

    def _emit(self, ev: Any) -> None:
        self._events.append(ev)

    def set_table_unlocked(self, unlocked: bool, caller: str) -> None:
        caller = _normalize_addr(caller)
        _require(caller == _normalize_addr(GOVERNANCE_ROUND), NotGovernance)
        self._table_unlocked = unlocked
        self._unlock_block = genesis_block_if_you_need_it()
        self._emit(EventTableUnlocked(unlocked_by=caller, block_ts=self._unlock_block))

    def transfer(self, from_addr: str, to_addr: str, amount: int, sender: str) -> None:
        from_addr = _normalize_addr(from_addr)
        to_addr = _normalize_addr(to_addr)
        sender = _normalize_addr(sender)
        _require(to_addr != "0x" + "0" * 40, TransferToZero)
        _require(amount > 0, ZeroAmount)
        bal = self._balances.get(from_addr, 0)
        _require(bal >= amount, ExceedsBalance)
        if sender != from_addr:
            allow = self._allowances.get((from_addr, sender), 0)
            _require(allow >= amount, ExceedsAllowance)
            self._allowances[(from_addr, sender)] = allow - amount

        fee = 0
        if self._transfer_fee_basis > 0 and self._fee_recipient != "0x" + "0" * 40:
            fee = (amount * self._transfer_fee_basis) // KON_BASIS_POINTS
            if fee > 0:
                amount -= fee
        self._balances[from_addr] = bal - amount - fee
        self._balances[to_addr] = self._balances.get(to_addr, 0) + amount
        if fee > 0:
            self._balances[self._fee_recipient] = self._balances.get(self._fee_recipient, 0) + fee
        self._emit(EventTransfer(from_addr=from_addr, to_addr=to_addr, amount=amount))

    def approve(self, owner: str, spender: str, amount: int) -> None:
        owner = _normalize_addr(owner)
        spender = _normalize_addr(spender)
        _require(owner != "0x" + "0" * 40, ZeroAddress)
        _require(spender != "0x" + "0" * 40, ZeroAddress)
        self._allowances[(owner, spender)] = amount

    def set_transfer_fee(self, basis: int, caller: str) -> None:
        caller = _normalize_addr(caller)
        _require(caller == _normalize_addr(GOVERNANCE_ROUND), NotGovernance)
        _require(basis <= KON_MAX_FEE_BASIS, FeeBasisTooHigh)
        self._transfer_fee_basis = basis

    def set_fee_recipient(self, recipient: str, caller: str) -> None:
        caller = _normalize_addr(caller)
        _require(caller == _normalize_addr(GOVERNANCE_ROUND), NotGovernance)
        _require(recipient != "0x" + "0" * 40, ZeroAddress)
        self._fee_recipient = _normalize_addr(recipient)

    def claim_seat(self, seat_id: int, knight: str, stake_amount: int, block_num: int) -> None:
        _require(0 <= seat_id < ROUND_TABLE_SEATS, InvalidSeatId)
        knight = _normalize_addr(knight)
        _require(self._table_unlocked, TableNotUnlocked)
        seat = self._seats[seat_id]
        _require(seat.status == SeatStatus.VACANT, SeatAlreadyClaimed)
        _require(stake_amount >= KON_MIN_STAKE_FOR_SEAT, InsufficientStake)
        bal = self._balances.get(knight, 0)
        _require(bal >= stake_amount, ExceedsBalance)

        self._balances[knight] = bal - stake_amount
        self._seats[seat_id] = RoundTableSeat(
            seat_id=seat_id,
            occupant=knight,
            stake_amount=stake_amount,
            claimed_at_block=block_num,
            status=SeatStatus.CLAIMED,
        )
        self._seat_by_knight[knight] = seat_id
        self._emit(EventSeatClaimed(seat_id=seat_id, knight=knight, stake_amount=stake_amount))

    def release_seat(self, seat_id: int, caller: str, block_num: int) -> None:
        _require(0 <= seat_id < ROUND_TABLE_SEATS, InvalidSeatId)
        caller = _normalize_addr(caller)
        seat = self._seats[seat_id]
        _require(seat.occupant == caller, NotAKnight)
        _require(seat.status == SeatStatus.CLAIMED, TableGuardDenied)

        amount = seat.stake_amount
        self._seats[seat_id] = RoundTableSeat(
            seat_id=seat_id,
            occupant="",
            stake_amount=0,
            claimed_at_block=0,
            status=SeatStatus.VACANT,
        )
        del self._seat_by_knight[caller]
        self._balances[caller] = self._balances.get(caller, 0) + amount

    def has_round_table_access(self, addr: str) -> bool:
        return _normalize_addr(addr) in self._seat_by_knight

    def get_seat_for_knight(self, addr: str) -> Optional[int]:
        return self._seat_by_knight.get(_normalize_addr(addr))

    def mint_kok(self, token_id: int, to_addr: str, caller: str) -> None:
        _require(0 <= token_id < KOK_COLLECTION_SIZE, KOKIndexOutOfRange)
        _require(not self._kok_minted[token_id], KOKAlreadyMinted)
        caller = _normalize_addr(caller)
        to_addr = _normalize_addr(to_addr)
        _require(caller == _normalize_addr(SEAT_REGISTRAR), NotRegistrar)
        _require(to_addr != "0x" + "0" * 40, ZeroAddress)

        self._kok_minted[token_id] = True
        self._kok_owners[token_id] = to_addr
        meta = KOK_METADATA[token_id]
        self._emit(EventKOKMinted(token_id=token_id, to_addr=to_addr, rarity=meta["rarity"]))

    def transfer_kok(self, token_id: int, from_addr: str, to_addr: str, sender: str) -> None:
        _require(0 <= token_id < KOK_COLLECTION_SIZE, KOKIndexOutOfRange)
        from_addr = _normalize_addr(from_addr)
        to_addr = _normalize_addr(to_addr)
        sender = _normalize_addr(sender)
        _require(self._kok_owners.get(token_id) == from_addr, NotKOKOwner)
        _require(sender == from_addr, NotKOKOwner)
        _require(to_addr != "0x" + "0" * 40, ZeroAddress)
        self._kok_owners[token_id] = to_addr

    def balance_of(self, addr: str) -> int:
        return self._balances.get(_normalize_addr(addr), 0)

    def allowance(self, owner: str, spender: str) -> int:
        return self._allowances.get((_normalize_addr(owner), _normalize_addr(spender)), 0)

    def total_supply(self) -> int:
        return self._total_supply

    def get_seat(self, seat_id: int) -> Optional[RoundTableSeat]:
        if 0 <= seat_id < ROUND_TABLE_SEATS:
            return self._seats[seat_id]
        return None

    def get_kok_owner(self, token_id: int) -> Optional[str]:
        return self._kok_owners.get(token_id)

    def get_kok_metadata(self, token_id: int) -> Optional[Dict[str, Any]]:
        if 0 <= token_id < KOK_COLLECTION_SIZE:
            return KOK_METADATA[token_id].copy()
        return None

    def get_events(self) -> List[Any]:
        return self._events.copy()

    def clear_events(self) -> None:
        self._events.clear()

    def seats_claimed_count(self) -> int:
        return sum(1 for s in self._seats.values() if s.status == SeatStatus.CLAIMED)

    def kok_minted_count(self) -> int:
        return sum(1 for v in self._kok_minted.values() if v)


def genesis_block_if_you_need_it() -> int:
    return int(time.time()) // 12


# ---------------------------------------------------------------------------
# EIP-712 style domain (for signing round-table access)
# ---------------------------------------------------------------------------


def get_eip712_domain() -> Dict[str, Any]:
    return {
        "name": "KnightsOfNear",
        "version": EIP712_VERSION,
        "chainId": 1,
        "verifyingContract": ROUND_TABLE_CORE,
    }


def hash_round_table_message(seat_id: int, knight: str, nonce: int) -> str:
    payload = f"{ROUND_TABLE_NAMESPACE}:{seat_id}:{knight}:{nonce}"
    return "0x" + hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Batch seat claims (EVM-safe cap)
# ---------------------------------------------------------------------------


def batch_claim_seats(
    engine: KnightsOfNearEngine,
    claims: List[Tuple[int, str, int]],
    block_num: int,
) -> None:
    _require(len(claims) <= MAX_CLAIM_PER_TX, ClaimBatchTooLarge)
    for seat_id, knight, stake in claims:
        engine.claim_seat(seat_id, knight, stake, block_num)


# ---------------------------------------------------------------------------
# KOK collection export (for frontends / TheRealm)
# ---------------------------------------------------------------------------

