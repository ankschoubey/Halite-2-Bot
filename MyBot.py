import time
import hlt
import logging
import math
import functools
game = hlt.Game("Frieza 2")
game_map = None
my_ships = None
command_queue = []
benchmark_factor = 7


def invert_dict(d):
    temp = {}
    for k, v in d.items():
        if type(v) == list:
            for i in v:
                temp[i] = k
                k += 0.01
        else:
            temp[v] = k
    return temp


@functools.lru_cache()
def distance_calculator(x, y, x1, y2):
    return abs(x - x1) + abs(y - y2)


def benchmark(no):
    return no + no % benchmark_factor


def number_of_unowned_planets():
    return len([0 for i in game_map.all_planets() if not i.is_owned()])


@functools.lru_cache()
def distance_to_planets(x, y):
    result = {}
    for planet in game_map.all_planets():
        result[planet.id] = distance_calculator(x, y, benchmark(planet.x), benchmark(planet.y))
    return result


def is_planet_unowned(planet):
    return not planet.is_owned()


def is_planet_unsecure(planet):
    return not planet.is_full()


@functools.lru_cache()
def prioritizer(x, y, priority_unowned=2):
    distances = distance_to_planets(benchmark(x), benchmark(y))
    remove_from_dist = []
    for k, v in distances.items():
        planet = game_map.get_planet(k)
        if is_planet_unowned(planet):
            distances[k] //= priority_unowned
        elif is_planet_unsecure(planet):
            distances[k] //= 2

    sort_by_distance = invert_dict(distances)
    distances_sorted = sorted(invert_dict(distances))

    planets = []

    for i in distances_sorted:
        planets.append(sort_by_distance[i])

    logging.info('Optimized Prioritizer: ' + str(planets))

    return planets, distances_sorted[0], is_planet_unowned(game_map.get_planet(planets[0]))


fighter = set()


def number_of_docked(game_map):
    me = game_map.get_me()
    return len([0 for ship in me.all_ships() if ship.owner == me.id])


def is_owned_by_me(planet, game_map):
    return planet.owner == game_map.my_id


def planet_distance_for_docked_ship(ship):
    if ship.planet:
        return ship.planet.x, ship.planet.y
    return ship.x, ship.y


@functools.lru_cache()
def nearby_enemy_ships(x, y):
    distances = {}
    for ship in [i for i in game_map._all_ships() if i not in my_ships]:

        x2, y2 = planet_distance_for_docked_ship(ship)

        distances[ship] = distance_calculator(
            benchmark(x), benchmark(y), benchmark(x2), benchmark(y2))
    sort_by_distance = invert_dict(distances)
    distances_sorted = sorted(sort_by_distance)

    enemy_ships = [sort_by_distance[i] for i in distances_sorted]

    return enemy_ships, round(distances_sorted[0])


def simplely_navigate(ship, target):
    global game_map
    return ship.navigate(
        ship.closest_point_to(target),
        game_map,
        speed=int(hlt.constants.MAX_SPEED),
        ignore_ships=False)


def fly_fighter(fighter):
    me = game_map.get_me()
    new_list = set()
    if len(fighter) == 0:
        return new_list

    targetted_ship = {}
    # ship: number_of_fighters
    ignore_list = []
    logging.info('Start of fighter')
    force = True

    for ids in list(fighter):
        ship = me.get_ship(ids)
        if not ship:
            continue

        enemy_ships, minimum_distance = nearby_enemy_ships(benchmark(ship.x), benchmark(ship.y))
        needed_distance = 40
        planets, p_distance, habitable = prioritizer(benchmark(ship.x), benchmark(ship.y))
        if not force and minimum_distance > needed_distance and p_distance < needed_distance and habitable:
            logging.info('Fighter no more' + str(minimum_distance) + ' ' +
                         str(len(enemy_ships)) + ' ' + str(100 - len(enemy_ships)))
            force = False
            continue

        benchmark_factor = len(enemy_ships) // 2
        logging.info('enemy_ships' + str(enemy_ships))
        for i in [j for j in enemy_ships if j.id not in ignore_list]:
            navigate_command = simplely_navigate(ship, i)
            logging.info('Navigate Command' + str(navigate_command))
            new_list.add(ids)
            if navigate_command:
                targetted_ship.setdefault(i.id, 0)
                targetted_ship[i.id] += 1
                if targetted_ship[i.id] >= 2:
                    ignore_list.append(i.id)
                command_queue.append(navigate_command)
                logging.info('command_queue' + str(command_queue))
                break
    logging.info('End of fly_fighter')
    return new_list


started = True
while True:
    # clear cache for updating data
    nearby_enemy_ships.cache_clear()
    prioritizer.cache_clear()
    command_queue = []
    visiting = []

    # update environment
    game_map = game.update_map()
    my_ships = game_map.get_me().all_ships()

    fighter = fly_fighter(fighter)

    total_planets = len(game_map.all_planets())
    total_unowned = number_of_unowned_planets()
    priority_unowned = total_planets - total_unowned
    priority_unowned = 1 if priority_unowned == 0 else priority_unowned
    for ship in game_map.get_me().all_ships():
        if started:
            started = False

            fighter.add(ship.id)
            continue
        number_of_ships = len(game_map.get_me().all_ships())

        if ship.isdocked() or ship.id in fighter:
            continue

        if math.log(number_of_ships - len(fighter)) / 10 > 10 and len(fighter) < 10:
            fighter.add(ship.id)
        planets, temp, temp2 = prioritizer(benchmark(ship.x), benchmark(ship.y),
                                           priority_unowned)

        for ids in planets:
            if ids in visiting:
                continue
            planet = game_map.get_planet(ids)
            logging.info('Planet Type = ' + str(type(planet)))
            if ship.can_dock(planet):
                logging.info('Ship' + str(ship.id) + ' can be docked on planet ' + str(ids))
                command_queue.append(ship.dock(planet))
                visiting.append(planet.id)
                break
            else:
                if planet.is_owned() and not is_owned_by_me(planet, game_map):
                    fighter.add(ship.id)
                    continue
                logging.info('Ship' + str(ship.id) + ' is going to planet ' + str(ids))

                navigate_command = simplely_navigate(ship, planet)
                logging.info('Navigation = ' + str(navigate_command))
                if navigate_command:
                    command_queue.append(navigate_command)
                    visiting.append(planet.id)
                    break
    logging.info('Final command_queue' + str(command_queue))
    game.send_command_queue(command_queue)
