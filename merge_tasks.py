import json
import argparse
import random
import collections

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', dest='files', nargs='+', required=True)
    parser.add_argument('-o', dest='output', required=True)

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--sort', action='store_true')
    group.add_argument('--reverse_sort', action='store_true')
    group.add_argument('--random', action='store_true')

    # if we want to sort by y axis
    parser.add_argument('--y', dest='sort_by_y', action='store_true')

    args = parser.parse_args()

    tasks_order_dict = collections.OrderedDict()

    for filename in args.files:
        try:
            with open(filename, 'r') as fp:
                tasks_subset = json.load(fp)
                for task in tasks_subset:
                    tasks_order_dict[tuple(task[:2])] = task[2]

        except IOError as e:
            print("Cannot open file %s with error: %s" % (filename, e))
        except ValueError as e:
            print("Failed to decode JSON: %s" % e)
        except Exception as e:
            print("Error occurs when reading file %s: %s" % (filename, e))

    tasks = [(xy[0], xy[1], rgb_hex)
             for xy, rgb_hex in tasks_order_dict.items()]

    sort_func = None
    if args.sort_by_y:
        # don't know why, but code format convert my lambda function to a real
        # function
        def sort_func(x): return (x[1], x[0])

    if args.sort:
        print("Sorting order in ascending order")
        tasks.sort(key=sort_func)
    elif args.reverse_sort:
        print("Sorting order in descending order")
        tasks.sort(key=sort_func, reverse=True)
    elif args.random:
        print("Shuffling task orders")
        random.shuffle(tasks)

    try:
        with open(args.output, "w") as fp:
            json.dump(tasks, fp)
        print("Writing %d tasks to %s" % (len(tasks), args.output))
    except IOError as e:
        print("Failed to write to output file %s: %s" % (args.output, e))
