import cv2
import argparse
import sys
import numpy as np
from matplotlib import pyplot as plt
from sklearn.cluster import KMeans
import matplotlib
import scipy.spatial.distance as distance
import scipy.ndimage
from kami import toArrays

font = cv2.FONT_HERSHEY_SIMPLEX
np.set_printoptions(linewidth=220)


def griddect(img, debug=False):
    gray = cv2.cvtColor(img,  cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize = 3)

    lines = cv2.HoughLines(edges, 2, np.pi/100, 320)
    v = []
    h = []
    for rho, theta in lines[0]:
        a = np.cos(theta)
        b = np.sin(theta)
        x0 = a*rho
        y0 = b*rho
        x1 = int(x0 + 1000*(-b))
        y1 = int(y0 + 1000*(a))
        x2 = int(x0 - 1000*(-b))
        y2 = int(y0 - 1000*(a))

        if int(a) == 0:
            h.append(y1)
        else:
            v.append(x1)

        if debug:
            cv2.line(img, (x1, y1), (x2, y2), (50, 50, 255), 2)

    height, width, channels = img.shape
    DEC = 0

    def dist(numArr):
        for i in range(len(numArr) - 1):
            x = numArr[i + 1] - numArr[i]
            if x > 5:
                yield x

    v_points = np.unique(np.round(np.array(sorted(v)), decimals=DEC))
    v_dist = list(dist(np.sort(v_points)))
    v_point_median = np.median(v_dist)

    h_points = np.unique(np.round(np.array(sorted(h)), decimals=DEC))
    h_dist = list(dist(np.sort(h_points)))
    h_point_median = np.median(h_dist)

    return v_point_median, h_point_median


def get_inside_boxes(image, v, h):
    height, width, channels = img.shape
    data = []
    hsv_img = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    for i in range(0, int(height), int(h)):
        row = []
        for j in range(0, int(width), int(v)):
            x = int(i + v/2)
            y = int(j + h/2)
            if x < height and y < width:
                row.append(img[x][y])

        if len(row) > 0:
            data.append(row)

    data = np.round(np.array(data), decimals=0)
    labels, numLabels = scipy.ndimage.label(data)

    return data


def gauss(img, size=7):
    kernel = np.ones((size, size), np.float32)/(size * size)
    return cv2.filter2D(img, -1, kernel)


def KBin(data, bins=4):
    w = data.shape[0]
    h = data.shape[1]
    image = data.reshape((w * h, 3))
    clt = KMeans(n_clusters=5)
    fit = clt.fit_predict(image)
    # quant = clt.cluster_centers_.astype("uint8")[fit]
    # return quant.reshape((w, h, 3))
    return fit.reshape((w, h))

def getNeighbours(point, dims):
    (x, y) = point
    (w, h) = dims
    if x > 0:
        yield (x-1, y)
    if x + 1 < w:
        yield (x+1, y)

    if y > 0:
        yield (x, y-1)
    if y + 1 < h:
        yield (x, y+1)


def floodFromPoint(data, localGroup, point, thresh=0, dims=(0, 0)):
    if localGroup[point]:
        return

    localGroup[point] = True
    for neigh in getNeighbours(point, dims):
        dist = int(distance.euclidean(
            map(int, data[point]),
            map(int, data[neigh]),
        ))
        # if debug: print point, '->', neigh, data[point], '->', data[neigh], '=', dist
        if dist < thresh:
            floodFromPoint(data, localGroup, neigh, thresh=thresh, dims=dims)


def customBin(data, l1thresh=0):
    w = data.shape[0]
    h = data.shape[1]
    outputData = np.zeros((w, h))
    undecidedPlaces = zip(*np.where(outputData == 0))
    # Find all values in the outputData with zeros.
    groupId = 1
    # While we have undecided areas, bin them
    while len(undecidedPlaces) > 0:
        # if debug: print 'Group %s' % groupId
        start = undecidedPlaces[0]
        localGroup = np.zeros((w, h), dtype=bool)
        floodFromPoint(data, localGroup, start, dims=(w, h), thresh=l1thresh)
        # localGroup is now populated
        for i in range(w):
            for j in range(h):
                if localGroup[i][j]:
                    # Remove from undecided places
                    undecidedPlaces.remove((i, j))
                    outputData[i][j] = groupId
        groupId += 1
    return outputData


def reduceBins(binnedData, data, l2thresh=30):
    w = binnedData.shape[0]
    h = binnedData.shape[1]
    maxVal = np.max(binnedData)

    # Keyed on [color][binIdx]
    finalBins = {}
    for i in range (1, int(maxVal) + 1):
        currentGroup = zip(*np.where(binnedData == i))

        hit = False
        # For each element in our current group
        for element in currentGroup:
            # We want to figure out if it matches an existing colour, or if
            # it's a new one. So we start by getting all existing groups of a
            # given colour:
            for fbColor in finalBins.keys():
                pointsInColourGroup = []
                # Get all the groups
                for grouping in finalBins[fbColor]:
                    if grouping == '_meta_': continue
                    pointsInColourGroup += finalBins[fbColor][grouping]

                matchScore = np.min([
                    distance.euclidean(
                        map(int, data[point]),
                        map(int, data[element])
                     ) for point in pointsInColourGroup
                ])
                if matchScore < l2thresh:
                    hit = (fbColor, data[element])
                    break

            if hit: break

        if not hit:
            # We start a new group
            finalBins[len(finalBins.keys())] = {
                0: currentGroup,
                '_meta_': data[currentGroup[0]]
            }
        else:
            (a, b) = hit
            finalBins[a][len(finalBins[a])] = currentGroup
            finalBins[a]['_meta_'] = b

    return toArrays(finalBins, w, h)


def binData(data, bins=4, l1thresh=0, l2thresh=0):
    return reduceBins(customBin(data, l1thresh=l1thresh), data, l2thresh=l2thresh)


colors = [
    (255, 0, 255),
    (255, 255, 0),
    (0, 0, 255),
    (0, 255, 0),
    (0, 255, 255),
]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('img', help="Path to image")
    parser.add_argument('--bins', type=int, help="Number of bins", default=3)
    parser.add_argument('--debug', action='store_true', help="Enable debug mode")
    parser.add_argument('--defaultSize', action='store_true', help="Override size detection with default 16 tall 10 wide")
    parser.add_argument('--l1thresh', type=int, default=40)
    parser.add_argument('--l2thresh', type=int, default=50)
    parser.add_argument('-vo', type=int, help="Override v", default=0)
    parser.add_argument('-ho', type=int, help="Oherride h", default=0)
    parser.add_argument('--out_base', type=str)


    args = parser.parse_args()

    img = cv2.imread(args.img)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    if not args.defaultSize:
        (v, h) = griddect(img, debug=args.debug)
        if debug:
            print 'Detected grid as v=%s, h=%s' % (v, h)
        if args.vo != 0:
            v = args.vo
        if args.ho != 0:
            h = args.ho
    else:
        height, width, channels = img.shape
        if width > height:
            h = np.round(float(height) / 10)
            v = np.round(float(width) / 16)
        else:
            h = np.round(float(height) / 16)
            v = np.round(float(width) / 10)

        h = int(h)
        v = int(v)

    color_data = get_inside_boxes(gauss(img, size=20), v, h)
    binnedColours, binnedGroups = binData(color_data, bins=args.bins, l1thresh=args.l1thresh, l2thresh=args.l2thresh)

    with open(args.out_base + '.c.txt', 'w') as handle:
        for row in binnedColours:
            handle.write('\t'.join(map(str, row)))
            handle.write('\n')

    with open(args.out_base + '.g.txt', 'w') as handle:
        handle.write(binnedGroups)

    if args.debug:
        for i in range(binnedColours.shape[0]):
            cv2.line(img, (i * v, 0), (i * v, height), (50, 50, 255), 2)

            for j in range(binnedColours.shape[1]):
                if j == 0:
                    cv2.line(img, (0, i * v), (width, i * v), (50, 50, 255), 2)

                y = i * v + v / 2
                x = j * h + h / 2
                z = binnedColours[i][j]

                # print i, j, x, y, z
                pos_a = (int(x), int(y) + 10 * (j % 3))
                pos = (int(x), int(y))
                # cv2.circle(img, pos, 7, colors[z], -1)
                # q = '.'.join([str(int(x)) for x in color_data[i][j]])
                cv2.putText(img, str(int(z)), pos, font, 2, (90,90,90), 2)

        plt.imshow(img)
        plt.show()
