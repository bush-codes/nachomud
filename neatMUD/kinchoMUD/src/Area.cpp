/*
 * Area.cpp
 *
 *  Created on: Aug 22, 2009
 *      Author: kincho
 */

#ifndef AREA_CPP
#define AREA_CPP

#include <iostream>

#include <cstdlib>
#include <string>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

#include "Mob.h"
#include "Room.cpp"

using namespace std;
using namespace rapidxml;

class Area
{
	private:
		int ad; //xml area descriptor
		string name;
		int numRooms;
		Room roomList[100];	//When/If stack space becomes a problem, move this out to heap
		int numDoors;
		Door doorList[100];	//When/If stack space becomes a problem, move this out to heap
		bool valid;

	public:
		Area() :
			valid(false)
		{
		}

		Area(const char *filename) :
			valid(true)
		{
			file<> f(filename);
			xml_document<> doc;
			doc.parse<0> (f.data());
			const xml_node<> * const areaRoot = doc.first_node();

			ad = atoi(areaRoot->first_attribute("ad")->value());
			name = string(areaRoot->first_node("name")->value());

			const xml_node<> * currentRoom = areaRoot->first_node("room");
			numRooms = 0;
			while (currentRoom != NULL)
			{
				roomList[numRooms] = Room(ad, currentRoom);
				currentRoom = currentRoom->next_sibling("room");
				++numRooms;
			}

			const xml_node<> * currentDoor = areaRoot->first_node("door");
			numDoors = 0;
			while (currentDoor != NULL)
			{
				doorList[numDoors] = Door(currentDoor);
				currentDoor = currentDoor->next_sibling("door");
				++numDoors;
			}
		}

		virtual ~Area()
		{

		}

		const int& getDescriptor() const
		{
			return ad;
		}

		const string& getName() const
		{
			return name;
		}

		Room& getRoom(const int& r)
		{
			if ((r < 0) || (r >= numRooms))
				throw "getRoom(): index out of bounds\n";
			return roomList[r];
		}

		const int& getNumRooms() const
		{
			return numRooms;
		}

		Door& getDoor(const int& d)
		{
			if ((d < 0) || (d >= numDoors))
				throw "getDoor(): index out of bounds\n";
			return doorList[d];
		}

		const int& getNumDoors() const
		{
			return numDoors;
		}

		const bool& isValid() const
		{
			return valid;
		}

		const string toString() const
		{
			string s = getName() + "\r\n\r\n";

			for (int i = 0; i < getNumRooms(); ++i)
			{
				s += roomList[i].toString() + "\r\n";
			}

			return s;
		}
};

#endif
