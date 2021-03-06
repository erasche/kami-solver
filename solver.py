import argparse
import sys
import copy
import scipy.spatial.distance as distance
import networkx as nx
import json
import time
from networkx.readwrite import json_graph
from kami import fromArrays


class Group:
    def __init__(self, points, colour=None, idx=0):
        self.points = points
        self.colour = colour
        self.idx = idx

    def touches(self, otherGroup):
        for a in self.points:
            for b in otherGroup.points:
                if distance.cityblock(a, b) == 1:
                    return True
        return False

    def __str__(self):
        return '<Group %s Colour="%s" len="%s" />' % (
                self.idx, self.colour.r + self.colour.g + self.colour.b, len(self.points))

    def __eq__(self, other):
        return self.idx == other.idx

    def __hash__(self):
        return self.idx


class Colour:
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

    def __str__(self):
        return '<Colour %s,%s,%s>' % (self.r, self.g, self.b)

    def __eq__(self, other):
        return self.r == other.r and self.g == other.g and self.b == other.b

    def __hash__(self):
        return self.r << 16 & self.g << 8 & self.b

    def json(self):
        return [self.r, self.g, self.b]


def reduceGraph(graph):
    g = graph.copy()

    equivalent_node_a = None
    equivalent_node_b = None
    for (a, b) in sorted(g.edges()):
        # If we have an set of nodes
        if a.colour == b.colour:
            equivalent_node_a = a
            equivalent_node_b = b
            # We quit immediately
            break

    # If we didn't find a node, then we return our graph immediately.
    if equivalent_node_a is None:
        return g

    # Otherwise, we need to make the processing and then return
    # reduceGraph(self) in case we missed any nodes (since we broke on first)
    a_neighs = list(nx.all_neighbors(g, equivalent_node_a))
    b_neighs = list(nx.all_neighbors(g, equivalent_node_b))
    # Remove for ease of access
    b_neighs.remove(equivalent_node_a)
    a_neighs.remove(equivalent_node_b)
    to_remove = []
    to_add = []
    for b_neighbour in b_neighs:
        if b_neighbour not in a_neighs:
            to_add.append((equivalent_node_a, b_neighbour))

        to_remove.append((equivalent_node_b, b_neighbour))

        # if a_neighbour not in b_neighs and \
                # a_neighbour != equivalent_node_b:
            # to_add.append((a_neighbour, equivalent_node_b))
        # to_remove.append((a_neighbour, equivalent_node_a))

    for (a, b) in to_remove:
        g.remove_edge(a, b)

    for (a, b) in to_add:
        g.add_edge(a, b)

    equivalent_node_a.points += equivalent_node_b.points
    g.remove_node(equivalent_node_b)

    return reduceGraph(g)


def serializeGraph(graph):
    data = {
        'directed': False,
        'graph': {},
        'links': [],
        'multigraph': False,
        'nodes': [],
    }
    node_list = list(graph.nodes())

    for (a, b) in graph.edges():
        data['links'].append({
            'source': node_list.index(a),
            'target': node_list.index(b),
        })

    for idx, node in enumerate(node_list):
        data['nodes'].append({
            'id': idx,
            'colour': node.colour.json(),
            'points': node.points,
            'size': len(node.points),
        })

    return data


def storeSolution(origGraph, solution, name_override=None):
    g = copy.deepcopy(origGraph)
    data = [serializeGraph(g)]
    for step in solution:
        print step, [x.idx for x in g.nodes()]
        g = applyStep(g, step)
        g = reduceGraph(g)
        data.append(serializeGraph(g))

    name = 'out.%s.json' % int(time.time())
    if name_override:
        name = name_override

    with open('force/' + name, 'w') as handle:
        handle.write(json.dumps(data))


def solve(new_graph, solution=None, maxAcceptable=0, orig=None):
    path = len(solution)
    if path > maxAcceptable:
        return


    colours_left = len(set([node.colour for node in new_graph.nodes()]))
    distinct_groups = len(new_graph.nodes())
    # We accept at most N moves.
    # If we have gotten to a path of length N, then coloursLeft must == 1.

    if not (maxAcceptable - path > colours_left - 2):
        return

    # Start out by reducing same coloured nodes
    if len(new_graph.nodes()) == 1:
        return solution

    # Now we mutate
    for node in list(sorted(new_graph.nodes())):
        # Get neighbours
        neighbours = list(nx.all_neighbors(new_graph, node))
        # And their colours
        neigh_colours = [x.colour for x in neighbours]
        # We can be assured they are not like ours due to reduceGraph
        for colour in neigh_colours:
            # We take a copy of our graph, and toggle the colour
            tmp_graph = new_graph.copy()
            xnode = [x for x in tmp_graph if x.idx == node.idx][0]
            xnode.colour = colour

            tmp_graph = reduceGraph(tmp_graph)
            x = solve(tmp_graph, solution=solution + [(node.idx, colour)], maxAcceptable=maxAcceptable, orig=orig)
            if x is not None:
                return x


def solveGraph(data, steps=0):
    G = nx.Graph()
    i = 0
    for colourGroup in data:
        # A single colour group
        for subGroup in data[colourGroup]:
            if subGroup == '_meta_': continue
            # A single logical node / region of coloured space
            group = Group(data[colourGroup][subGroup],
                    colour=Colour(*data[colourGroup]['_meta_']),
                    idx=i)
            i += 1
            G.add_node(group)

    # Find touching groups
    for node_a in sorted(G.nodes()):
        for node_b in sorted(G.nodes()):
            if node_a == node_b:
                continue

            if node_a.touches(node_b):
                G.add_edge(node_a, node_b)

    orig = copy.deepcopy(G)
    initialSolution = []
    # biggestNode = max(G.nodes(), key=lambda x: len(x.points))
    # x73 = [node for node in G.nodes() if [3, 7] in node.points][0]
    # initialSolution = [
        # (x73.idx, Colour(0, 0, 0)),
        # (x73.idx, Colour(0, 12, 255)),
        # (32, Colour(255, 0, 0)),
        # (1, Colour(255, 238, 0)),
        # (1, Colour(255, 0, 0)),
        # (0, Colour(0, 0, 0)),
    # ]

    for step in initialSolution:
        applyStep(G, step)
        G = reduceGraph(G)

    # Initial reduction
    G = reduceGraph(G)
    return orig, solve(G, solution=initialSolution, maxAcceptable=steps, orig=orig)


def applyStep(graph, step):
    node = [x for x in graph if x.idx == step[0]][0]
    node.colour = step[1]
    graph = reduceGraph(graph)
    return graph


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('colourData', type=argparse.FileType('r'), help="Path to X.c.txt data")
    parser.add_argument('groupsData', type=argparse.FileType('r'), help="Path to X.g.txt data")
    parser.add_argument('--steps', type=int, default=5)
    args = parser.parse_args()

    colourData = []
    for line in args.colourData:
        data = line.strip().split('\t')
        colourData.append(map(int, data))

    parsedData = fromArrays(colourData, args.groupsData)
    original_graph, solution = solveGraph(parsedData, steps=args.steps)

    storeSolution(original_graph, solution, name_override='final.json')
