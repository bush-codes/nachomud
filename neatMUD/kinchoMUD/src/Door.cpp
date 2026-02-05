/*
 * Door.cpp
 *
 *  Created on: Oct 19, 2010
 *      Author: kincho
 */

#ifndef DOOR_CPP
#define DOOR_CPP

#include <iostream>
#include <cstdlib>
#include <string>

#include "rapidxml-1.13/rapidxml.hpp"

using namespace std;
using namespace rapidxml;

class Door
{
	private:
		int dd;
		bool closed;
		bool valid;

	public:
		Door() : valid(false)
		{

		}

		Door(const xml_node<> * const doorRoot) : closed(false), valid(true)
		{
			dd = atoi(doorRoot->first_attribute("dd")->value());

			string c = string(doorRoot->first_attribute("closed")->value());
			if(c == "true")
				closed = true;
		}

		virtual ~Door()
		{

		}

		const bool isOpen() const
		{
			return !isClosed();
		}

		const bool& isClosed() const
		{
			return closed;
		}

		void open()
		{
			closed = false;
		}

		void close()
		{
			closed = true;
		}

		const bool& isValid() const
		{
			return valid;
		}
};

#endif
