"""Full regression run: everything the grinder claims to do, checked in one go."""
import unrealsdk
from bl2_modern.features import grinder as g
pc = unrealsdk.find_all("WillowPlayerController")[-1]
inv = pc.GetPawnInventoryManager()
cur = unrealsdk.find_enum("ECurrencyType")
pc.PlayerReplicationInfo.AddCurrencyOnHand(cur.CURRENCY_Credits, 2000000)
g.how_many.value = 3
g.cost_per_level.value = 100
results = []

def seed(kind_rarity, n, stage=40):
    pool = unrealsdk.find_object("ItemPoolDefinition", g.POOLS[kind_rarity])
    for _ in range(n):
        for m in g._spawn_from_pool(pc, pool, stage):
            inv.AddBackpackInventory(m)

def pk():
    return len(list(unrealsdk.find_all("WillowPickup")))

# 1a. grind, straight to the backpack
g.loot_on_ground.value = False
seed(("weapon", 3), 3)
feed = [i for i in g._backpack(pc) if g._kind(i) == "weapon" and g._rarity(i) == 3][:3]
bi, bm = len(g._backpack(pc)), g._money(pc)
g._grind(pc, feed)
ai, am = len(g._backpack(pc)), g._money(pc)
results.append(("grind to backpack: 3 in, 1 out", ai - bi == -2))
results.append(("grind: money charged", am < bm))

# 1b. grind, dropped on the ground the way the game drops loot
g.loot_on_ground.value = True
seed(("weapon", 3), 3)
feed = [i for i in g._backpack(pc) if g._kind(i) == "weapon" and g._rarity(i) == 3][:3]
bi, bp_ = len(g._backpack(pc)), pk()
g._grind(pc, feed)
results.append(("grind to ground: 3 consumed", len(g._backpack(pc)) - bi == -3))
results.append(("grind to ground: loot appeared in the world", pk() > bp_))
g.loot_on_ground.value = False

# 2. grind refuses a mixed rarity, and takes nothing
mixed = [i for i in g._backpack(pc) if g._kind(i) == "weapon"][:2]
seed(("weapon", 9), 1)
mixed += [i for i in g._backpack(pc) if g._rarity(i) == 9][:1]
bi = len(g._backpack(pc))
g._grind(pc, mixed)
results.append(("grind: refuses mixed rarity, takes nothing", len(g._backpack(pc)) == bi))

# 3. grind refuses with no money
saved = g._money(pc)
pc.PlayerReplicationInfo.AddCurrencyOnHand(cur.CURRENCY_Credits, -saved)
seed(("weapon", 3), 3)
feed = [i for i in g._backpack(pc) if g._kind(i) == "weapon" and g._rarity(i) == 3][:3]
bi = len(g._backpack(pc))
g._grind(pc, feed)
results.append(("grind: refuses when broke, takes nothing", len(g._backpack(pc)) == bi))
pc.PlayerReplicationInfo.AddCurrencyOnHand(cur.CURRENCY_Credits, 2000000)

# 4. skins are never offered
skins = [i for i in g._backpack(pc) if g._kind(i) == "skin"]
results.append(("skins excluded", all(g._kind(s) in g.NOT_GRINDABLE for s in skins)))

# 5. every kind present maps to a pool
kinds = {(g._kind(i), g._rarity(i)) for i in g._backpack(pc)}
unmapped = [(k, r) for k, r in kinds if k not in g.NOT_GRINDABLE and r >= 0 and g._pool_for(k, r) is None]
results.append((f"every kind maps to a pool (unmapped: {unmapped})", not unmapped))

# 6. perfect needs 2+
g.how_many.value = 1
bi = len(g._backpack(pc))
g._choose_items(pc, "perfect")
results.append(("perfect refuses at count 1", len(g._backpack(pc)) == bi))
g.how_many.value = 3

# 7. level-less gear
from bl2_modern.features import levelless as L
lvl = pc.PlayerReplicationInfo.ExpLevel
seed(("weapon", 4), 1, stage=max(1, lvl - 10))
low = [i for i in g._backpack(pc) if g._kind(i) == "weapon" and i.GameStage < lvl]
if low:
    gun = low[-1]
    uid = int(gun.DefinitionData.UniqueId)
    was_dmg = gun.InstantHitDamage
    n_before = len(g._backpack(pc))
    L.mark(gun)
    same = [i for i in g._backpack(pc) if int(i.DefinitionData.UniqueId) == uid]
    results.append(("level-less: catches up to your level", bool(same) and same[0].GameStage == lvl))
    results.append(("level-less: damage actually rescaled", bool(same) and same[0].InstantHitDamage > was_dmg))
    results.append(("level-less: exactly one copy, not two", len(same) == 1))
    results.append(("level-less: item count unchanged", len(g._backpack(pc)) == n_before))
    L._forget(uid)
    results.append(("level-less: can be turned off again", uid not in L._ids()))
else:
    results.append(("level-less: could not seed a low-level gun", False))

print()
for name, ok in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\n{sum(1 for _, o in results if o)}/{len(results)} passed")
