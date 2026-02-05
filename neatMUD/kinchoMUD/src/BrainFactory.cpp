/*
 * BrainFactory.cpp
 *
 *  Created on: Sep 8, 2009
 *      Author: kincho
 */

#ifndef BRAINFACTORY_CPP
#define BRAINFACTORY_CPP

#include "MobBrain.h"

#include <sstream>
#include <map>
#include <vector>
#include <stdlib.h>
#include <time.h>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

class BrainFactory
{
	private:
		map<int, MobBrain*> BrainTrust;

		BrainFactory() // Private constructor
		{
		}
		BrainFactory(const BrainFactory&); // Prevent copy-construction
		BrainFactory& operator=(const BrainFactory&); // Prevent assignment


	public:
		static BrainFactory& Instance()
		{
			static BrainFactory singleton;
			return singleton;
		}
		void addBrain(const int& mfd, const string mobName, const int& numActions)
		{
			BrainTrust.insert(make_pair(mfd, new MobBrain(mobName.c_str(), numActions)));
		}

		MobBrain& getBrain(const int& mfd)
		{
			return *(BrainTrust[mfd]);
		}

		~BrainFactory()
		{
			map<int, MobBrain*>::iterator iter;

			for (iter = BrainTrust.begin(); iter != BrainTrust.end(); ++iter)
			{
				delete (iter->second);
			}
		}
};

#endif
