/*
 * Direction.cpp
 *
 *  Created on: Sep 9, 2009
 *      Author: kincho
 */
#ifndef DIRECTION_CPP
#define DIRECTION_CPP

#include <string>

using namespace std;

#define NUM_DIRECTIONS 10
enum Direction
{
	northwest, north, northeast, east, southeast, south, southwest, west, up, down
};
static const Direction directionArray[] = { northwest, north, northeast, east, southeast, south, southwest, west, up, down };
static const string directionName[] = { "northwest", "north", "northeast", "east", "southeast", "south", "southwest", "west", "up", "down" };
static const Direction& string2Direction(const string& s) //this method is a hack, figure out something better
{
	int d = 0;
	while ((d < NUM_DIRECTIONS) && (directionName[d] != s))
		++d;

	if (d < 10)
		return directionArray[d];
	else
		throw "getDirection: invalid string s";
}

static const int string2DirectionDescriptor(const string& s) //this method is a hack of a hack, figure out something better
{
	int d = 0;
	while ((d < NUM_DIRECTIONS) && (directionName[d] != s))
		++d;

	if (d < 10)
		return directionArray[d];
	else
		return -1;
}

#endif
