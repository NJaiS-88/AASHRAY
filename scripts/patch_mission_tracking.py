with open('route_engine/src/services/missionTracking.service.js', 'r', encoding='utf-8') as f:
    c = f.read()

target = """  try {
    const record = await prisma.missionRouteState.upsert({"""

replacement = """  try {
    const upsertPromise = prisma.missionRouteState.upsert({"""

assert target in c, "target not found"
c = c.replace(target, replacement, 1)

target2 = """    });

    return record;
  } catch (err) {"""

replacement2 = """    });

    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Prisma database connection timeout')), 1000)
    );

    const record = await Promise.race([upsertPromise, timeoutPromise]);
    return record;
  } catch (err) {"""

assert target2 in c, "target2 not found"
c = c.replace(target2, replacement2, 1)

with open('route_engine/src/services/missionTracking.service.js', 'w', encoding='utf-8') as f:
    f.write(c)

print('Successfully patched missionTracking.service.js')
