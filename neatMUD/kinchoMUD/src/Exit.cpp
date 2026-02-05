/*
 * Exit.cpp
 *
 *  Created on: Sep 8, 2009
 *      Author: kincho
 */

#ifndef EXIT_CPP
#define EXIT_CPP

#include <iostream>
#include <cstdlib>
#include <string>

#include "rapidxml-1.13/rapidxml.hpp"

#include "Door.cpp"
#include "Direction.cpp"

using namespace std;
using namespace rapidxml;

class Exit
{
	private:
		int ad;			//Area descriptor (unique)
		int rd;			//Room descriptor (unique)
		int dd;			//Door descriptor (shared) -1 if no door
		Direction dir;
		bool valid;

	public:
		Exit() : valid(false)
		{
		}

		Exit(const int &a, const xml_node<> * const exitRoot) :
			valid(true)
		{
			//If no area is defined in the xml, default to room's area
			xml_attribute<> * area = exitRoot->first_attribute("area");
			ad = (area != NULL) ? atoi(area->value()) : a;

			//Room descriptor must be defined, or exit has no destination
			//TODO sanity checking on this
			rd = atoi(exitRoot->first_attribute("room")->value());

			//If no door is defined in the xml, default to null
			//Come back to this when doors are more sophisticated
			//Change into node within exit instead of attribute
			xml_attribute<> * door = exitRoot->first_attribute("door");
			dd = (door != NULL) ? atoi(door->value()) : -1;

			dir = string2Direction(exitRoot->first_attribute("direction")->value());
		}

		virtual ~Exit()
		{

		}

		const int& getAreaDescriptor() const
		{
			return ad;
		}

		const int& getRoomDescriptor() const
		{
			return rd;
		}

		const bool hasDoor() const
		{
			return (dd >= 0);
		}

		const int& getDoorDescriptor() const
		{
			//Make this exception?
			assert(dd >= 0);
			return dd;
		}

		const Direction& getDirection() const
		{
			return dir;
		}

		const bool& isValid() const
		{
			return valid;
		}
};

#endif
