/*
 * MasterStatList.cpp
 *
 *  Created on: Jan 2, 2010
 *      Author: kincho
 */

#ifndef MASTERSTATMAP_CPP
#define MASTERSTATMAP_CPP

#include <vector>
#include <map>

#include <iostream>

#include <cstdlib>
#include <string>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

using namespace std;
using namespace rapidxml;

class MasterStatMap
{
		private:
			map<int, string> statMapForward;
			map<string, int> statMapReverse;
			vector<bool> match;
			vector<int> container;

		MasterStatMap() // Private constructor
		{
			file<> f("data/master.stats");
			xml_document<> doc;
			doc.parse<0> (f.data());
			const xml_node<> * const masterRoot = doc.first_node();

			const xml_node<> * currentStat = masterRoot->first_node("stat");
			while (currentStat != NULL)
			{
				int sd = atoi(currentStat->first_attribute("sd")->value());
				string name = string(currentStat->first_attribute("name")->value());

				statMapForward.insert(make_pair(sd, name));
				statMapReverse.insert(make_pair(name, sd));

				match.push_back("t" == currentStat->first_attribute("match")->value());

				if("t" == currentStat->first_attribute("container")->value());
					container.push_back(sd);

				currentStat = currentStat->next_sibling("stat");
			}

		}

		MasterStatMap(const MasterStatMap&); // Prevent copy-construction
		MasterStatMap& operator=(const MasterStatMap&); // Prevent assignment


	public:
		static MasterStatMap& Instance()
		{
			static MasterStatMap singleton;
			return singleton;
		}

		const string& getStatName(const int& sd)
		{
			return statMapForward[sd];
		}

		const int& getStatDescriptor(const string& s)
		{
			return statMapReverse[s];
		}

		const int getNumStats()
		{
			return statMapForward.size();
		}

		const int& getContainerStatDescriptor(const int& cd)
		{
			return container[cd];
		}

		const int getNumContainers()
		{
			return container.size();
		}

		const bool isMatchedStat(const int& sd)
		{
			return match[sd];
		}

		~MasterStatMap()
		{
		}
};

#endif
