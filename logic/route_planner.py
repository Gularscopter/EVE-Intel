# logic/route_planner.py
import itertools
import logging

def find_shortest_path(distance_matrix, start_node, waypoints):
    """
    Finner den korteste ruten som besøker alle veipunkter, med start fra start_node.
    Dette er en brute-force løsning på Traveling Salesman Problem, som er effektiv
    for et lite antall veipunkter (typisk for EVE-handelsruter).

    Args:
        distance_matrix (dict): En nestet ordbok med avstand (hopp) mellom alle noder.
                                f.eks. distance_matrix[system1][system2] = 5
        start_node (int): System-ID for startpunktet.
        waypoints (list): En liste med unike system-IDer som må besøkes.

    Returns:
        tuple: En tuppel som inneholder (ordnet_rute, total_distanse).
               'ordnet_rute' er en liste med system-IDer i optimal rekkefølge.
               'total_distanse' er det totale antallet hopp for ruten.
               Returnerer (None, float('inf')) hvis en rute ikke kan kalkuleres.
    """
    if not waypoints:
        return [start_node], 0
    
    # Sørg for at waypoints er en liste uten start_node
    waypoints_to_visit = [wp for wp in waypoints if wp != start_node]
    if not waypoints_to_visit:
        return [start_node], 0

    best_path = None
    min_distance = float('inf')

    # Generer alle mulige rekkefølger (permutasjoner) av veipunktene
    for path_permutation in itertools.permutations(waypoints_to_visit):
        current_distance = 0
        current_node = start_node
        
        # Kalkuler distansen for denne permutasjonen
        try:
            # Fra start til første veipunkt
            current_distance += distance_matrix[current_node][path_permutation[0]]
            
            # Mellom veipunktene
            for i in range(len(path_permutation) - 1):
                from_node = path_permutation[i]
                to_node = path_permutation[i+1]
                current_distance += distance_matrix[from_node][to_node]
            
            # Sjekk om denne ruten er den beste så langt
            if current_distance < min_distance:
                min_distance = current_distance
                best_path = (start_node,) + path_permutation

        except KeyError as e:
            # Dette skjer hvis et system i ruten ikke finnes i avstandsmatrisen,
            # som indikerer en ufullstendig rute.
            logging.warning(f"Kunne ikke finne avstand i matrisen for nøkkel: {e}. Hopper over permutasjon.")
            continue # Gå til neste permutasjon

    if best_path:
        return list(best_path), min_distance
    else:
        return None, float('inf')