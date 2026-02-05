/*
 * Action.cpp
 *
 *  Created on: Sep 15, 2009
 *      Author: kincho
 */

#ifndef ACTION_CPP
#define ACTION_CPP

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

using namespace std;
using namespace rapidxml;

class Action
{
	private:
		int ad; //unique action name
		string name;
		string description;
		int numFields;
		bool valid;

	public:
		Action() :
			valid(false)
		{
		}

		Action(const char *filename) :
			valid(true)
		{
			file<> f(filename);
			xml_document<> doc;
			doc.parse<0> (f.data());
			const xml_node<> * const actRoot = doc.first_node();

			ad = atoi(actRoot->first_attribute("ad")->value());
			numFields = atoi(actRoot->first_attribute("numfields")->value());
			description = string(actRoot->first_attribute("description")->value());
			name = string(actRoot->first_attribute("name")->value());
		}

		Action(int newAD, string newName, string newDescription, int newNumFields) :
			ad(newAD), name(newName), description(newDescription), numFields(newNumFields), valid(true)
		{
		}

		const int& getDescriptor() const
		{
			return ad;
		}

		const bool& isValid() const
		{
			return valid;
		}

		const string& getDescription() const
		{
			return description;
		}

		const string& getName() const
		{
			return name;
		}

		const int& getNumFields() const
		{
			return numFields;
		}
};

#endif
