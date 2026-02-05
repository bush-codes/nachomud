/*
 * Room.cpp
 *
 *  Created on: Aug 22, 2009
 *      Author: kincho
 */

#ifndef ROOM_CPP
#define ROOM_CPP

#include <iostream>
#include <cstdlib>
#include <string>

#include "rapidxml-1.13/rapidxml.hpp"

#include "Exit.cpp"

using namespace std;
using namespace rapidxml;

class Room
{
	private:
		int ad; //area descriptor
		int rd; //xml room descriptor (consider array for overlap)
		string name;
		string description;
		Exit exitList[NUM_DIRECTIONS];
		int numExits;
		bool valid;

	public:
		Room() :
			valid(false)
		{
		}

		Room(const int &a, const xml_node<> * const roomRoot) :
			valid(true)
		{
			ad = a;
			rd = atoi(roomRoot->first_attribute("rd")->value());
			name = string(roomRoot->first_node("name")->value());
			description = string(roomRoot->first_node("description")->value());

			const xml_node<> * currentExit = roomRoot->first_node("exit");
			numExits = 0;
			while (currentExit != NULL)
			{
				Exit e(ad, currentExit);
				exitList[e.getDirection()] = e;
				currentExit = currentExit->next_sibling("exit");
				++numExits;
			}
		}

		virtual ~Room()
		{

		}

		const int& getAreaDescriptor() const
		{
			return ad;
		}

		const int& getDescriptor() const
		{
			return rd;
		}

		const string& getName() const
		{
			return name;
		}

		const string& getDescription() const
		{
			return description;
		}

		const int& getNumExits() const
		{
			return numExits;
		}

		Exit& getExit(Direction d)
		{
			return exitList[d];
		}

		const bool& isValid() const
		{
			return valid;
		}

		const string toString() const
		{
			string s = getName() + "\r\n" + getDescription() + "\r\n";

			string exitString = "[exits:";

			bool foundExit = false;
			for (int i = 0; i < NUM_DIRECTIONS; ++i)
			{
				if (exitList[i].isValid())
				{
					exitString += " " + directionName[i];
					foundExit = true;
				}
			}

			if (foundExit == false)
				exitString += string(" none") + string("]\r\n");

			return s + exitString + string("]\r\n");
		}
};

#endif
