/*
 * Battle.cpp
 *
 *  Created on: Sep 8, 2009
 *      Author: kincho
 */

#ifndef BATTLE_CPP
#define BATTLE_CPP

#include "Mob.h"

#include <map>
#include <vector>
#include <stdlib.h>
#include <time.h>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

class Battle
{
	private:
		Battle() // Private constructor
		{
		}
		Battle(const Battle&); // Prevent copy-construction
		Battle& operator=(const Battle&); // Prevent assignment


	public:
		static Battle& Instance()
		{
			static Battle singleton;
			return singleton;
		}

		bool startBattle(Mob& sourceMob, Mob& targetMob)
		{

			/********************************RTNEATZ YO*******************************************/
			targetMob.requestOrganism();
			double fitness = 0;
			/********************************RTNEATZ DONE*****************************************/

			Console::Instance().display("You enter a battle!!!");
			Console::Instance().newLine();

			string command;

			bool sourcesTurn = true;

			while (sourceMob.getStat("hp").getCurrent() > 0 && targetMob.getStat("hp").getCurrent() > 0 && command != "run")
			{
				Console::Instance().display("Player HP: ");
				Console::Instance().displayInt(sourceMob.getStat("hp").getCurrent());
				Console::Instance().display(" Player MP: ");
				Console::Instance().displayInt(sourceMob.getStat("mp").getCurrent());
				Console::Instance().newLine();

				Console::Instance().display("Enemy HP: ");
				Console::Instance().displayInt(targetMob.getStat("hp").getCurrent());
				Console::Instance().display(" Enemy MP: ");
				Console::Instance().displayInt(targetMob.getStat("mp").getCurrent());
				Console::Instance().newLine();

				if (sourcesTurn)
				{
					Console::Instance().newLine();
					Console::Instance().displayln(sourceMob.getName() + "'s Turn");
					Console::Instance().display("Battle Action");
					command = Console::Instance().prompt();

					if (command == "hit")
					{
						int dmg = rand() % 6; //TODO strength stat calcs here...

						Console::Instance().newLine();
						Console::Instance().display("You hit " + targetMob.getName() + " for ");
						Console::Instance().displayInt(dmg);
						Console::Instance().displayln(" damage!");

						targetMob.damage(dmg);
					}
				}

				else
				{
					Console::Instance().newLine();
					Console::Instance().displayln(targetMob.getName() + "'s Turn");

					int numInputs = BrainFactory::Instance().getBrain(targetMob.getFamilyDescriptor()).getNumInputs();
					double input[numInputs];
					for(int i = 0; i < numInputs; ++i)
						input[i] = 0;
					input[0] = targetMob.getStat("hp").getCurrent();
					input[1] = targetMob.getStat("mp").getCurrent();

					pair<int, int> decisionPair = targetMob.chooseAction(input);
					int decision = decisionPair.first;
					int target = decisionPair.second;

					if (decision >= 1)
					{
						int dmg = 1;
						fitness += dmg;
						Console::Instance().display(targetMob.getName() + " hit you for ");
						Console::Instance().displayInt(dmg);
						Console::Instance().displayln(" damage!");
						sourceMob.damage(dmg);
					}
					else
					{
						fitness = 0;
						Console::Instance().displayln(targetMob.getName() + " sits idly.");
					}
				}
				sourcesTurn = !sourcesTurn;
			}

			if (sourceMob.getStat("hp").getCurrent() <= 0)
			{
				Console::Instance().displayln(targetMob.getName() + " killed you. ");
				Console::Instance().displayln("Game Over.");
				Console::Instance().prompt();
				targetMob.retireOrganism(2 * fitness); //send double fitness for winning battle
				return false;
			}
			else
			{
				Console::Instance().displayln("You killed " + targetMob.getName() + "!");
				Console::Instance().display("Press any key to exit battle...");
				Console::Instance().prompt();
				targetMob.retireOrganism(fitness); //send huge fitness hit for losing battle.
				return true;
			}
		}

		string autoBattle(Mob& sourceMob, Mob& targetMob)
		{
			Console::Instance().displayln("You enter a battle!!!");
			Console::Instance().newLine();
			string command;

			bool sourcesTurn = true;

			while(true)
			{
				/********************************RTNEATZ YO*******************************************/
				targetMob.requestOrganism();
				double fitness = 0;
				/********************************RTNEATZ DONE*****************************************/

				int numCures = 0;
				int numHits = 0;
				int numIdles = 0;
				int numFires = 0;
				int numPoisons = 0;
				int numCrits = 0;

				bool sourceMobPoisoned = false;

				while (sourceMob.getStat("hp").getCurrent() > 0 && targetMob.getStat("hp").getCurrent() > 0 && command != "run")
				{
					if (sourcesTurn)
					{
						if(sourceMobPoisoned)
						{
							sourceMob.damage(5);
							fitness += 5;
						}

						int dmg = 1; //damage mob
						targetMob.damage(dmg);
					}

					else
					{
						int numInputs = BrainFactory::Instance().getBrain(targetMob.getFamilyDescriptor()).getNumInputs();
						double input[numInputs];
						for(int i = 0; i < numInputs; ++i)
							input[i] = 0;
						input[0] = targetMob.getStat("hp").getCurrent();
						input[1] = targetMob.getStat("mp").getCurrent();

						pair<int, int> decisionPair = targetMob.chooseAction(input);
						int decision = decisionPair.first;
						int target = decisionPair.second;

						if (decision == 15) //Mob Hits
						{
							numHits++;
							int dmg = 5;
							fitness += dmg;
							sourceMob.damage(dmg);
						}
						else if (decision == 16) //Mob casts cure
						{
							numCures++;
							if(targetMob.getStat("mp").getCurrent() > 0)
							{
								fitness += 100;
								targetMob.setStat("hp", targetMob.getStat("hp").getMax());
								targetMob.setStat("mp", targetMob.getStat("mp").getCurrent() - 1);
							}
						}
						else if (decision == 17) //Mob casts fire
						{
							numFires++;
							if(targetMob.getStat("mp").getCurrent() > 0)
							{
								fitness += 600;
								sourceMob.damage(600);
								targetMob.setStat("mp", targetMob.getStat("mp").getCurrent() - 1);
							}
						}
						else if (decision == 18) //Mob casts poison
						{
							numPoisons++;
							if(targetMob.getStat("mp").getCurrent() > 0)
							{
								targetMob.setStat("mp", targetMob.getStat("mp").getCurrent() - 1);
								sourceMobPoisoned = true;
								//fitness is added as source mob is damaged, handled in bool check below
							}
						}
						else if (decision == 19) //Mob crits
						{
							numCrits++;
							fitness += 15;
							sourceMob.damage(15);
							targetMob.damage(5);
						}
						else
						{
							numIdles++;
						}
					}

					sourcesTurn = !sourcesTurn;
				}

				targetMob.retireOrganism(fitness);

				Console::Instance().display("fitness: ");
				Console::Instance().displayInt(fitness);
				Console::Instance().newLine();
				Console::Instance().display("Num Hits: ");
				Console::Instance().displayInt(numHits);
				Console::Instance().newLine();
				Console::Instance().display("Num Cures: ");
				Console::Instance().displayInt(numCures);
				Console::Instance().newLine();
				Console::Instance().display("Num Idle: ");
				Console::Instance().displayInt(numIdles);
				Console::Instance().newLine();
				Console::Instance().display("Num Fires: ");
				Console::Instance().displayInt(numFires);
				Console::Instance().newLine();
				Console::Instance().display("Num Poisons: ");
				Console::Instance().displayInt(numPoisons);
				Console::Instance().newLine();
				Console::Instance().display("Num Crits: ");
				Console::Instance().displayInt(numCrits);
				Console::Instance().newLine();

				targetMob.setStat("hp", targetMob.getStat("hp").getMax());
				targetMob.setStat("mp", targetMob.getStat("mp").getMax());
			}
			return "";
		}

		string autoBattle2(Mob& sourceMob, Mob& targetMob)
		{
			Console::Instance().displayln("--- Individualized Party Combat System ---");
			Console::Instance().newLine();

			int partySize = 3;
			int enemySize = 1;
			int numMobs = partySize + enemySize;

			Mob mobList[4];
			mobList[0] = Mob(0, "Paladin", 0, 0, "data/mobs/paladin.pc");
			mobList[1] = Mob(1, "Magician", 0, 0, "data/mobs/magician.pc");
			mobList[2] = Mob(2, "Sorcerer", 0, 0, "data/mobs/sorcerer.pc");
			mobList[3] = Mob(3, "Skeleton A", 0, 0, "data/mobs/skeletona.pc");

//			Mob mobList[10];
//			mobList[0] = Mob(0, "data/mobs/paladin.pc");
//			mobList[1] = Mob(1, "data/mobs/darkknight.pc");
//			mobList[2] = Mob(2, "data/mobs/magician.pc");
//			mobList[3] = Mob(3, "data/mobs/cleric.pc");
//			mobList[4] = Mob(4, "data/mobs/sorcerer.pc");
////			mobList[0] = Mob(0, "data/mobs/redonionknight.pc");
////			mobList[1] = Mob(1, "data/mobs/blueonionknight.pc");
////			mobList[2] = Mob(2, "data/mobs/greenonionknight.pc");
////			mobList[3] = Mob(3, "data/mobs/purpleonionknight.pc");
////			mobList[4] = Mob(4, "data/mobs/whiteonionknight.pc");
//			mobList[5] = Mob(5, "data/mobs/skeletona.pc");
//			mobList[6] = Mob(6, "data/mobs/skeletonb.pc");
//			mobList[7] = Mob(7, "data/mobs/skeletonc.pc");
//			mobList[8] = Mob(8, "data/mobs/skeletond.pc");
//			mobList[9] = Mob(9, "data/mobs/skeletone.pc");

			int numEncounters = 0;

			while(numEncounters < 250000)
			{
				Console::Instance().newLine();
				Console::Instance().display("---- ");
				Console::Instance().displayInt(numEncounters);
				Console::Instance().display(" ----");
				Console::Instance().newLine();

//				*******************************RTNEATZ YO******************************************
				mobList[0].requestOrganism();
				mobList[1].requestOrganism();
				mobList[2].requestOrganism();
				mobList[3].requestOrganism();
//				mobList[4].requestOrganism();
//				mobList[5].requestOrganism();
//				mobList[6].requestOrganism();
//				mobList[7].requestOrganism();
//				mobList[8].requestOrganism();
//				mobList[9].requestOrganism();
//				*******************************RTNEATZ DONE****************************************

				int karma[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

				int numIdles[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numHits[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numCures[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numFires[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numPoisons[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numReaps[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numDeaths[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

				int numCovers[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numRegens[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numRefresh[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numProtects[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numSleeps[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numHastes[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numBlinks[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numDrains[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numBerserks[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

				int damageDealt[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int damageReceived[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int healingDealt[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int whoopsieDealt[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

				//Over time status
				bool isRegened[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isRefreshed[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isPoisoned[10] = {false, false, false, false, false, false, false, false, false, false};

				//Other status
				bool isCovered[10] = {false, false, false, false, false, false, false, false, false, false};
				int isCovering[10] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
				int coveredBy[10] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
				bool isProtected[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isSlept[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isHasted[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isBlinked[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isBerserked[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isAlive[10] = {true, true, true, true, true, true, true, true, true, true};

				int partyDeaths = 0;
				int skeletonDeaths = 0;

				int numTurns = 0;

				//While a member of our party is alive and there have been fewer than 100 turns
				while((mobList[0].getStat("hp").getCurrent() > 0 &&
					  mobList[1].getStat("hp").getCurrent() > 0 &&
					  mobList[2].getStat("hp").getCurrent() > 0 /*||
					  mobList[3].getStat("hp").getCurrent() > 0 ||
					  mobList[4].getStat("hp").getCurrent() > 0 */) &&
					  numTurns < 1000)
				{
					int whoseTurn = 0;
					bool mobReady = false;
					while(!mobReady)
					{
						//Check to see if any of the mobs are ready to act
						for(int i = 0; i < numMobs && !mobReady; ++i)
						{
							if(mobList[i].getStat("turn").getCurrent() >= 100)
							{
								whoseTurn = i;

								if(isSlept[i])
								{
									isSlept[i] = false;
									mobList[i].getStat("turn").setCurrent(mobList[i].getStat("turn").getCurrent() - 100);
								}
								else
									mobReady = true;
							}
						}

						//If no mobs are prepared to act, increment all of the mobs turn counter based on their speed
						for(int i = 0; i < numMobs && !mobReady; ++i)
						{
							if(mobList[i].getStat("hp").getCurrent() > 0)
							{
								mobList[i].getStat("turn").setCurrent(mobList[i].getStat("turn").getCurrent() + mobList[i].getStat("spd").getCurrent());

								if(isHasted[i])
									mobList[i].getStat("turn").setCurrent(mobList[i].getStat("turn").getCurrent() + mobList[i].getStat("spd").getCurrent());

								//Regen
								int rot = 0;
								if(isRegened[i])
								{
									rot = mobList[i].getStat("hp").getMax() / 50;
									if(rot <= 0)
										rot = 1;

									if(mobList[i].getStat("hp").getCurrent() + rot > mobList[i].getStat("hp").getMax())
										mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getMax());
									else
										mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getCurrent() + rot);
								}

								//Refresh
								if(isRefreshed[i])
								{
									rot = mobList[i].getStat("mp").getMax() / 25;
									if(rot <= 0)
										rot = 1;

									if(mobList[i].getStat("mp").getCurrent() + rot > mobList[i].getStat("mp").getMax())
										mobList[i].getStat("mp").setCurrent(mobList[i].getStat("mp").getMax());
									else
										mobList[i].getStat("mp").setCurrent(mobList[i].getStat("mp").getCurrent() + rot);
								}

								//Poison
								int dot = 0;
								if(isPoisoned[i])
								{
									dot = mobList[i].getStat("hp").getMax() / 100;
									if(dot <= 0)
										dot = 1;

									mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getCurrent() - dot);
									damageReceived[i] += dot;
								}

								//Check for DoT death
								if(mobList[i].getStat("hp").getCurrent() <= 0 && isAlive[i])
								{
									isAlive[i] = false;
									++numDeaths[i];
//									mobList[i].setStat("turn", 0);

									//isCovering[coveredBy[i]] == i
									isCovered[isCovering[i]] = false;
									coveredBy[isCovering[i]] = isCovering[i];
									isCovered[i] = false;
									coveredBy[i] = i;
									Console::Instance().displayln(mobList[i].getName() + " has fallen.");

									if(i >= partySize)
									{
										isAlive[i] = true;
										Console::Instance().displayln(mobList[i].getName() + " has risen.");
										mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getMax());
									}
								}
							}
						}
					}

					//Acknowledge this mob is getting their turn
					++numTurns;
					mobReady = false;
					mobList[whoseTurn].getStat("turn").setCurrent(mobList[whoseTurn].getStat("turn").getCurrent() - 100);

					//Create the input sensors so our mob can make a decision
					int numInputs = BrainFactory::Instance().getBrain(mobList[whoseTurn].getFamilyDescriptor()).getNumInputs();
					double input[numInputs];
					for(int i = 0; i < numInputs; ++i)
						input[i] = 0;

					//Party position
					input[0] = 0;
					int i = 1;
					for(int j = 0; j < numMobs; ++j)
					{
						for(int k = 0; k < MasterStatMap::Instance().getNumContainers(); ++k)
						{
							//For every mob, place every container stat into the current mob's inputs
							//TODO kink mess with this shitpile till it works
							if(j < partySize)
								input[i] = mobList[j].getStat(MasterStatMap::Instance().getContainerStatDescriptor(k)).getCurrent();
							++i;
						}
					}

					pair<int, int> decisionPair = mobList[whoseTurn].chooseAction(input);
					int decision = decisionPair.first;
					int target = decisionPair.second;

					//forces the skellies to target this mob
					bool forceTarget = false;
					if(forceTarget && whoseTurn >= partySize)
						target = 1;

					bool randomTarget = true;
					if(randomTarget && whoseTurn >= partySize)
						target = (rand() % partySize);

					//Is the action hostile?
					bool hostile = (decision == 15) ||
									(decision == 17) ||
									(decision == 18) ||
									(decision == 19) ||
									(decision == 23) ||
									(decision == 27);

					if(hostile && isCovered[target] && mobList[coveredBy[target]].getStat("hp").getCurrent() <= 0)
					{
						isCovered[target] = false;
						coveredBy[target] = target;
					}

					//Disallow friendly fire or stray healing
					//If a party member
					if(whoseTurn < partySize)
					{
						if(hostile)
						{
							while(mobList[(target % enemySize) + partySize].getStat("hp").getCurrent() <= 0)
							{
								++target;
							}

							//Mod by # of foes for true target relative to foes
							target %= enemySize;
							//Add party size to find appropriate place in mobList
							target += partySize;

						}
						else
						{
							while(mobList[(target % partySize)].getStat("hp").getCurrent() <= 0)
							{
								++target;
							}

							//Mod by # of party members for true target
							target %= partySize;
						}
					}
					else  //Enemy
					{
						if(hostile)
						{
							while(mobList[(target % partySize)].getStat("hp").getCurrent() <= 0)
							{
								++target;
							}

							target %= partySize;
						}
						else
						{
							while(mobList[(target % enemySize) + partySize].getStat("hp").getCurrent() <= 0)
							{
								++target;
							}

							target %= enemySize;
							target += partySize;
						}
					}

					//If our target is sleeping, wake them and reset their turn counter
					if(isSlept[target] && (decision != 27))
					{
						isSlept[target] = false;
						mobList[target].getStat("turn").setCurrent(0);
					}

					int damage = 0;
					int healing = 0;

					if (decision == 15) //Mob hits
					{
						++numHits[whoseTurn];

						Console::Instance().displayln(mobList[whoseTurn].getName() + " attacks " + mobList[target].getName() + ".");

						if(isAlive[target])
						{
							//If our target is being covered by an ally who is awake
							if(isCovered[target] && !isSlept[coveredBy[target]])
							{
								Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
								target = coveredBy[target];
							}

							//base damage * (source str / target vit)
							damage = (10 + mobList[whoseTurn].getStat("lvl").getCurrent()) * ((double)mobList[whoseTurn].getStat("str").getCurrent() / (double)mobList[target].getStat("vit").getCurrent());

							if((rand() % 100) <= 10 + ((double)mobList[whoseTurn].getStat("dex").getCurrent() / (double)mobList[target].getStat("dex").getCurrent()))
							{
								damage *= 2;
								Console::Instance().displayln(mobList[whoseTurn].getName() + " scores a critical hit!");
							}

							if(isProtected[target])
								damage /= 2;

							if(isBerserked[whoseTurn])
								damage *= 2;
							if(isBerserked[target])
								damage *= 2;

							if(isBlinked[target])
							{
								damage = 0;
								isBlinked[target] = false;
								Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
							}
							else
							{
								mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);
								Console::Instance().display(mobList[target].getName() + " takes ");
								Console::Instance().displayInt(damage);
								Console::Instance().displayln(" points of damage.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
						}
					}
					else if (decision == 16) //Mob casts cure
					{
						++numCures[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Cure on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//cost + (wil - avg wil for lvl)
								healing = 2*(cost + mobList[whoseTurn].getStat("wil").getCurrent() - (2.5 * mobList[whoseTurn].getStat("lvl").getCurrent()));

								//Heal only to max, record amount healed for log
								if(mobList[target].getStat("hp").getCurrent() + healing > mobList[target].getStat("hp").getMax())
									healing = mobList[target].getStat("hp").getMax() - mobList[target].getStat("hp").getCurrent();

								mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() + healing);

								Console::Instance().display(mobList[target].getName() + " recovers ");
								Console::Instance().displayInt(healing);
								Console::Instance().displayln(" points of damage.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Cure on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 17) //Mob casts fire
					{
						++numFires[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Fire on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//If our target is being covered by an ally who is awake
								if(isCovered[target] && !isSlept[coveredBy[target]])
								{
									Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
									target = coveredBy[target];
								}

								if(isBlinked[target])
								{
									isBlinked[target] = false;
									Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
								}
								else
								{
									//2(cost + int - avg int for lvl)
									//TODO kink use elemental weaknesses to eventually turn this into the powerhouse it should be
									damage = 2 * (cost + mobList[whoseTurn].getStat("int").getCurrent() - (2.5 * mobList[whoseTurn].getStat("lvl").getCurrent()));

									if((rand() % 100) <= 10 + ((double)mobList[whoseTurn].getStat("int").getCurrent() / (double)mobList[target].getStat("wil").getCurrent()))
									{
										damage /= 2;
										Console::Instance().displayln(mobList[target].getName() + " resists!");
									}

									mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);
									Console::Instance().display(mobList[target].getName() + " takes ");
									Console::Instance().displayInt(damage);
									Console::Instance().displayln(" points of damage.");
								}
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Fire on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 18) //Mob casts poison
					{
						++numPoisons[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() * 0.05);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Poison on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//If our target is being covered by an ally who is awake
								if(isCovered[target] && !isSlept[coveredBy[target]])
								{
									Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
									target = coveredBy[target];
								}

								if(!isPoisoned[target])
								{
									if(isBlinked[target])
									{
										isBlinked[target] = false;
										Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
									}
									else
									{
										karma[whoseTurn] += 50;
										damage = 5 * ((double)mobList[whoseTurn].getStat("int").getCurrent() / (double)mobList[target].getStat("wil").getCurrent());

										mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);
										Console::Instance().display(mobList[target].getName() + " takes ");
										Console::Instance().displayInt(damage);
										Console::Instance().displayln(" points of damage.");

										isPoisoned[target] = true;
										Console::Instance().displayln(mobList[target].getName() + " is poisoned.");
									}
								}
								else
								{
									Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
								}
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Poison on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 19) //Mob uses reap
					{
						++numReaps[whoseTurn];

						Console::Instance().displayln(mobList[whoseTurn].getName() + " uses Reaper on " + mobList[target].getName() + ".");

						if(isAlive[target])
						{
							//If our target is being covered by an ally who is awake
							if(isCovered[target] && !isSlept[coveredBy[target]])
							{
								Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
								target = coveredBy[target];
							}

							damage = (mobList[whoseTurn].getStat("hp").getCurrent() / 10);
							mobList[whoseTurn].getStat("hp").setCurrent(mobList[whoseTurn].getStat("hp").getCurrent() - damage);
							Console::Instance().display(mobList[whoseTurn].getName() + " takes ");
							Console::Instance().displayInt(damage);
							Console::Instance().displayln(" points of damage.");
							//Special case to record damage received
							damageReceived[whoseTurn] += damage;

							//base damage * (source str / target vit)
							damage += (10 + mobList[whoseTurn].getStat("lvl").getCurrent()) * ((double)mobList[whoseTurn].getStat("str").getCurrent() / (double)mobList[target].getStat("vit").getCurrent());

							if((rand() % 100) <= 10 + ((double)mobList[whoseTurn].getStat("dex").getCurrent() / (double)mobList[target].getStat("dex").getCurrent()))
							{
								damage *= 2;
								Console::Instance().displayln(mobList[whoseTurn].getName() + " scores a critical hit!");
							}

							if(isProtected[target])
								damage /= 2;

							if(isBerserked[whoseTurn])
								damage *= 2;
							if(isBerserked[target])
								damage *= 2;

							if(isBlinked[target])
							{
								damage = 0;
								isBlinked[target] = false;
								Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
							}
							else
							{
								mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);
								Console::Instance().display(mobList[target].getName() + " takes ");
								Console::Instance().displayInt(damage);
								Console::Instance().displayln(" points of damage.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
						}
					}
					else if (decision == 21) //Mob casts regen
					{
						++numRegens[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Regen on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isRegened[target])
							{
								karma[whoseTurn] += 50;
								isRegened[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is regened.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Regen on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 22) //Mob casts refresh
					{
						++numRefresh[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 3);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Refresh on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isRefreshed[target])
							{
								karma[whoseTurn] += 200;
								isRefreshed[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is refreshed.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Refresh on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 23) //Mob casts drain
					{
						++numDrains[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Drain on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//If our target is being covered by an ally who is awake
								if(isCovered[target] && !isSlept[coveredBy[target]])
								{
									Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
									target = coveredBy[target];
								}

								if(isBlinked[target])
								{
									isBlinked[target] = false;
									Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
								}
								else
								{
									//2(cost + int - avg int for lvl)
									//TODO kink dark elemental?
									damage = cost + mobList[whoseTurn].getStat("int").getCurrent() - (2.5 * mobList[whoseTurn].getStat("lvl").getCurrent());

									if((rand() % 100) <= 10 + ((double)mobList[whoseTurn].getStat("int").getCurrent() / (double)mobList[target].getStat("wil").getCurrent()))
									{
										damage /= 2;
										Console::Instance().displayln(mobList[target].getName() + " resists!");
									}

									mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);

									Console::Instance().display(mobList[target].getName() + " takes ");
									Console::Instance().displayInt(damage);
									Console::Instance().displayln(" points of damage.");


									//Heal only to max, record amount healed for log
									healing = damage;
									if(mobList[whoseTurn].getStat("hp").getCurrent() + healing > mobList[whoseTurn].getStat("hp").getMax())
										healing = mobList[whoseTurn].getStat("hp").getMax() - mobList[whoseTurn].getStat("hp").getCurrent();

									mobList[whoseTurn].getStat("hp").setCurrent(mobList[whoseTurn].getStat("hp").getCurrent() + healing);

									Console::Instance().display(mobList[whoseTurn].getName() + " recovers ");
									Console::Instance().displayInt(healing);
									Console::Instance().displayln(" points of damage.");

									//To prevent recording a whoopsie, or twice with damage
									healing = 0;
								}
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Drain on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 24) //Mob casts protect
					{
						++numProtects[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Protect on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isProtected[target])
							{
								karma[whoseTurn] += 100;
								isProtected[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is protected.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Protect on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 25) //Mob uses berserk
					{
						++numBerserks[whoseTurn];

						Console::Instance().displayln(mobList[whoseTurn].getName() + " uses Berserk.");

						if(!isBerserked[whoseTurn])
						{
							isBerserked[whoseTurn] = true;
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is berserked.");
						}
						else
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unaffected.");
					}
					else if (decision == 26) //Mob casts haste
					{
						++numHastes[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 4);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Haste on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isHasted[target])
							{
								karma[whoseTurn] += 150;
								isHasted[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is hasted.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Haste on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 27) //Mob casts sleep
					{
						++numSleeps[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Sleep on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//If our target is being covered by an ally who is awake
								if(isCovered[target] && !isSlept[coveredBy[target]])
								{
									Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
									target = coveredBy[target];
								}

								if(!isSlept[target])
								{
									karma[whoseTurn] += 25;
									isSlept[target] = true;
									Console::Instance().displayln(mobList[target].getName() + " is slept.");
								}
								else
								{
									Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
								}
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Sleep on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 28) //Mob casts blink
					{
						++numBlinks[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Blink on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isBlinked[target])
							{
								karma[whoseTurn] += 25;
								isBlinked[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is blinked.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Blink on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 29) //Mob uses cover
					{
						++numCovers[whoseTurn];

						Console::Instance().displayln(mobList[whoseTurn].getName() + " uses Cover on " + mobList[target].getName() + ".");

						if(whoseTurn==target)
							isCovered[whoseTurn] = false;
						else
							isCovered[target] = true;

						isCovering[whoseTurn] = target;
						coveredBy[target] = whoseTurn;
					}
					else //Mob idles
					{
						Console::Instance().displayln(mobList[whoseTurn].getName() + " idles.");
						++numIdles[whoseTurn];
					}

					//Record damage, healing, and check for whoopsies
					damageReceived[target] += damage;
					damageDealt[whoseTurn] += damage;
					healingDealt[whoseTurn] += healing;

					if((whoseTurn < partySize && target < partySize)||(whoseTurn >= partySize && target >= partySize))
						whoopsieDealt[whoseTurn] += damage;
					if((whoseTurn < partySize && target >= partySize)||(whoseTurn >= partySize && target < partySize))
						whoopsieDealt[whoseTurn] += healing;

					//Check for target's death
					if(mobList[target].getStat("hp").getCurrent() <= 0 && isAlive[target])
					{
						isAlive[target] = false;
						++numDeaths[target];
//						mobList[target].setStat("turn", 0);

						isCovered[isCovering[target]] = false;
						coveredBy[isCovering[target]] = isCovering[target];
						isCovered[target] = false;
						coveredBy[target] = target;

						Console::Instance().displayln(mobList[target].getName() + " has fallen.");

						if(target >= partySize)
						{
							isAlive[target] = true;
							Console::Instance().displayln(mobList[target].getName() + " has risen.");
							mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getMax());
						}
					}
				}

				for(int i = 0; i < partySize; ++i)
				{
					partyDeaths += numDeaths[i];
				}

				for(int i = 0; i < enemySize; ++i)
				{
					skeletonDeaths += numDeaths[i + partySize];
				}

				//paladin
				//dark knight
				//magician
				//cleric
				//sorcerer

				int fitness[10];
				fitness[0] = numTurns + skeletonDeaths + karma[0] + ((double)(damageDealt[0] + healingDealt[0])/numTurns);
				fitness[1] = numTurns + skeletonDeaths + karma[1] + ((double)(damageDealt[1] + healingDealt[1])/numTurns);
				fitness[2] = numTurns + skeletonDeaths + karma[2] + ((double)(damageDealt[2] + healingDealt[2])/numTurns);
				fitness[3] = damageDealt[2] + healingDealt[2];
//				fitness[0] = /*(skeletonDeaths * 100) + */damageDealt[0] + healingDealt[0] - whoopsieDealt[0];
//				fitness[1] = /*(skeletonDeaths * 100) + */damageDealt[1] + healingDealt[1] - whoopsieDealt[1];
//				fitness[2] = /*(skeletonDeaths * 100) + */damageDealt[2] + healingDealt[2] - whoopsieDealt[2];
//				fitness[3] = /*(skeletonDeaths * 100) + */damageDealt[3] + healingDealt[3] - whoopsieDealt[3];
//				fitness[4] = /*(skeletonDeaths * 100) + */damageDealt[4] + healingDealt[4] - whoopsieDealt[4];
//				fitness[0] = (skeletonDeaths * 100) + damageDealt[0] + healingDealt[0] - whoopsieDealt[0];
//				fitness[1] = (skeletonDeaths * 100) + damageDealt[1] + healingDealt[1] - whoopsieDealt[1];
//				fitness[2] = (skeletonDeaths * 100) + damageDealt[2] + healingDealt[2] - whoopsieDealt[2];
//				fitness[3] = (skeletonDeaths * 100) + damageDealt[3] + healingDealt[3] - whoopsieDealt[3];
//				fitness[4] = (skeletonDeaths * 100) + damageDealt[4] + healingDealt[4] - whoopsieDealt[4];
//				fitness[5] = damageDealt[5] - whoopsieDealt[5];
//				fitness[6] = damageDealt[6] - whoopsieDealt[6];
//				fitness[7] = damageDealt[7] - whoopsieDealt[7];
//				fitness[8] = damageDealt[8] - whoopsieDealt[8];
//				fitness[9] = damageDealt[9] - whoopsieDealt[9];

				for(int i = 0; i < numMobs; ++i)
				{
					if(fitness[i] < 0)
						fitness[i] = 0;

					mobList[i].retireOrganism(fitness[i]);
				}

				Console::Instance().display("------------- Encounter ");
				Console::Instance().displayInt(numEncounters);
				Console::Instance().display("-------------");
				Console::Instance().newLine();

				++numEncounters;

				Console::Instance().display("Turns survived: ");
				Console::Instance().displayInt(numTurns);
				Console::Instance().newLine();

				Console::Instance().display("Party Deaths: ");
				Console::Instance().displayInt(partyDeaths);
				Console::Instance().newLine();

				Console::Instance().display("Skeleton Deaths: ");
				Console::Instance().displayInt(skeletonDeaths);
				Console::Instance().newLine();

				for(int i = 0; i < numMobs; ++i)
				{
					Console::Instance().displayln("------");
					Console::Instance().displayln(mobList[i].getName());
					Console::Instance().displayln("------");
					Console::Instance().display("Fitness: ");
					Console::Instance().displayInt(fitness[i]);
					Console::Instance().newLine();
					Console::Instance().display("Hits: ");
					Console::Instance().displayInt(numHits[i]);
					Console::Instance().newLine();
					Console::Instance().display("Cures: ");
					Console::Instance().displayInt(numCures[i]);
					Console::Instance().newLine();
					Console::Instance().display("Covers: ");
					Console::Instance().displayInt(numCovers[i]);
					Console::Instance().newLine();
					Console::Instance().display("Reaps: ");
					Console::Instance().displayInt(numReaps[i]);
					Console::Instance().newLine();
					Console::Instance().display("Berserks: ");
					Console::Instance().displayInt(numBerserks[i]);
					Console::Instance().newLine();
					Console::Instance().display("Drains: ");
					Console::Instance().displayInt(numDrains[i]);
					Console::Instance().newLine();
					Console::Instance().display("Fires: ");
					Console::Instance().displayInt(numFires[i]);
					Console::Instance().newLine();
					Console::Instance().display("Poisons: ");
					Console::Instance().displayInt(numPoisons[i]);
					Console::Instance().newLine();
					Console::Instance().display("Sleeps: ");
					Console::Instance().displayInt(numSleeps[i]);
					Console::Instance().newLine();
					Console::Instance().display("Regens: ");
					Console::Instance().displayInt(numRegens[i]);
					Console::Instance().newLine();
					Console::Instance().display("Protects: ");
					Console::Instance().displayInt(numProtects[i]);
					Console::Instance().newLine();
					Console::Instance().display("Refresh: ");
					Console::Instance().displayInt(numRefresh[i]);
					Console::Instance().newLine();
					Console::Instance().display("Hastes: ");
					Console::Instance().displayInt(numHastes[i]);
					Console::Instance().newLine();
					Console::Instance().display("Blinks: ");
					Console::Instance().displayInt(numBlinks[i]);
					Console::Instance().newLine();
					Console::Instance().display("Deaths: ");
					Console::Instance().displayInt(numDeaths[i]);
					Console::Instance().newLine();
					Console::Instance().display("Damage Dealt: ");
					Console::Instance().displayInt(damageDealt[i]);
					Console::Instance().newLine();
					Console::Instance().display("Healing Dealt: ");
					Console::Instance().displayInt(healingDealt[i]);
					Console::Instance().newLine();
					Console::Instance().display("Whoopsies: ");
					Console::Instance().displayInt(whoopsieDealt[i]);
					Console::Instance().newLine();
					Console::Instance().display("Damage Received: ");
					Console::Instance().displayInt(damageReceived[i]);
					Console::Instance().newLine();
					Console::Instance().display("Sleep: ");
					Console::Instance().displayBool(isSlept[i]);
					Console::Instance().newLine();
					Console::Instance().display("Poisoned: ");
					Console::Instance().displayBool(isPoisoned[i]);
					Console::Instance().newLine();
					Console::Instance().display("Regen: ");
					Console::Instance().displayBool(isRegened[i]);
					Console::Instance().newLine();
					Console::Instance().display("Protect: ");
					Console::Instance().displayBool(isProtected[i]);
					Console::Instance().newLine();
					Console::Instance().display("Refreshed: ");
					Console::Instance().displayBool(isRefreshed[i]);
					Console::Instance().newLine();
					Console::Instance().display("Haste: ");
					Console::Instance().displayBool(isHasted[i]);
					Console::Instance().newLine();
					Console::Instance().display("Alive: ");
					Console::Instance().displayBool(isAlive[i]);
					Console::Instance().newLine();

					mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getMax());
					mobList[i].getStat("mp").setCurrent(mobList[i].getStat("mp").getMax());
					mobList[i].getStat("turn").setCurrent(0);
				}
			}

			return "";
		}

		string autoBattle3(Mob& sourceMob, Mob& targetMob)
		{
			Console::Instance().displayln("--- Totalitarian Party Combat System ---");
			Console::Instance().newLine();

			int partySize = 2;
			int enemySize = 1;
			int numMobs = partySize + enemySize;

			Mob mobList[4];
			mobList[0] = Mob(0, "Paladin", 0, 0, "data/mobs/paladin.pc");
			mobList[1] = Mob(1, "Magician", 0, 0, "data/mobs/magician.pc");
			mobList[2] = Mob(2, "Sorcerer", 0, 0, "data/mobs/sorcerer.pc");
			mobList[3] = Mob(3, "Skeleton A", 0, 0, "data/mobs/skeletona.pc");

//			Mob mobList[10];
//			mobList[0] = Mob(0, "data/mobs/paladin.pc");
//			mobList[1] = Mob(1, "data/mobs/darkknight.pc");
//			mobList[2] = Mob(2, "data/mobs/magician.pc");
//			mobList[3] = Mob(3, "data/mobs/cleric.pc");
//			mobList[4] = Mob(4, "data/mobs/sorcerer.pc");
////			mobList[0] = Mob(0, "data/mobs/redonionknight.pc");
////			mobList[1] = Mob(1, "data/mobs/blueonionknight.pc");
////			mobList[2] = Mob(2, "data/mobs/greenonionknight.pc");
////			mobList[3] = Mob(3, "data/mobs/purpleonionknight.pc");
////			mobList[4] = Mob(4, "data/mobs/whiteonionknight.pc");
//			mobList[5] = Mob(5, "data/mobs/skeletona.pc");
//			mobList[6] = Mob(6, "data/mobs/skeletonb.pc");
//			mobList[7] = Mob(7, "data/mobs/skeletonc.pc");
//			mobList[8] = Mob(8, "data/mobs/skeletond.pc");
//			mobList[9] = Mob(9, "data/mobs/skeletone.pc");

			int numEncounters = 0;

			while(true)
			{
				Console::Instance().newLine();
				Console::Instance().display("---- ");
				Console::Instance().displayInt(numEncounters);
				Console::Instance().display(" ----");
				Console::Instance().newLine();

//				*******************************RTNEATZ YO******************************************
				mobList[0].requestOrganism();
				mobList[1].requestOrganism();
				mobList[2].requestOrganism();
				mobList[3].requestOrganism();
//				mobList[4].requestOrganism();
//				mobList[5].requestOrganism();
//				mobList[6].requestOrganism();
//				mobList[7].requestOrganism();
//				mobList[8].requestOrganism();
//				mobList[9].requestOrganism();
//				*******************************RTNEATZ DONE****************************************

				int karma[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

				int numIdles[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numHits[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numCures[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numFires[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numPoisons[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numReaps[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numDeaths[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

				int numCovers[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numRegens[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numRefresh[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numProtects[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numSleeps[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numHastes[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numBlinks[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numDrains[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int numBerserks[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

				int damageDealt[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int damageReceived[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int healingDealt[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
				int whoopsieDealt[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

				//Over time status
				bool isRegened[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isRefreshed[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isPoisoned[10] = {false, false, false, false, false, false, false, false, false, false};

				//Other status
				bool isCovered[10] = {false, false, false, false, false, false, false, false, false, false};
				int isCovering[10] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
				int coveredBy[10] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
				bool isProtected[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isSlept[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isHasted[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isBlinked[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isBerserked[10] = {false, false, false, false, false, false, false, false, false, false};
				bool isAlive[10] = {true, true, true, true, true, true, true, true, true, true};

				int partyDeaths = 0;
				int skeletonDeaths = 0;

				int numTurns = 0;

				//While a member of our party is alive and there have been fewer than 100 turns
				while((mobList[0].getStat("hp").getCurrent() > 0 &&
					  mobList[1].getStat("hp").getCurrent() > 0 &&
					  mobList[2].getStat("hp").getCurrent() > 0 /*||
					  mobList[3].getStat("hp").getCurrent() > 0 ||
					  mobList[4].getStat("hp").getCurrent() > 0 */) &&
					  numTurns < 1000)
				{
					int whoseTurn = 0;
					bool mobReady = false;
					while(!mobReady)
					{
						//Check to see if any of the mobs are ready to act
						for(int i = 0; i < numMobs && !mobReady; ++i)
						{
							if(mobList[i].getStat("turn").getCurrent() >= 100)
							{
								whoseTurn = i;

								if(isSlept[i])
								{
									isSlept[i] = false;
									mobList[i].getStat("turn").setCurrent(mobList[i].getStat("turn").getCurrent() - 100);
								}
								else
									mobReady = true;
							}
						}

						//If no mobs are prepared to act, increment all of the mobs turn counter based on their speed
						for(int i = 0; i < numMobs && !mobReady; ++i)
						{
							if(mobList[i].getStat("hp").getCurrent() > 0)
							{
								mobList[i].getStat("turn").setCurrent(mobList[i].getStat("turn").getCurrent() + mobList[i].getStat("spd").getCurrent());

								if(isHasted[i])
									mobList[i].getStat("turn").setCurrent(mobList[i].getStat("turn").getCurrent() + mobList[i].getStat("spd").getCurrent());

								//Regen
								int rot = 0;
								if(isRegened[i])
								{
									rot = mobList[i].getStat("hp").getMax() / 50;
									if(rot <= 0)
										rot = 1;

									if(mobList[i].getStat("hp").getCurrent() + rot > mobList[i].getStat("hp").getMax())
										mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getMax());
									else
										mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getCurrent() + rot);
								}

								//Refresh
								if(isRefreshed[i])
								{
									rot = mobList[i].getStat("mp").getMax() / 25;
									if(rot <= 0)
										rot = 1;

									if(mobList[i].getStat("mp").getCurrent() + rot > mobList[i].getStat("mp").getMax())
										mobList[i].getStat("mp").setCurrent(mobList[i].getStat("mp").getMax());
									else
										mobList[i].getStat("mp").setCurrent(mobList[i].getStat("mp").getCurrent() + rot);
								}

								//Poison
								int dot = 0;
								if(isPoisoned[i])
								{
									dot = mobList[i].getStat("hp").getMax() / 100;
									if(dot <= 0)
										dot = 1;

									mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getCurrent() - dot);
									damageReceived[i] += dot;
								}

								//Check for DoT death
								if(mobList[i].getStat("hp").getCurrent() <= 0 && isAlive[i])
								{
									isAlive[i] = false;
									++numDeaths[i];
//									mobList[i].setStat("turn", 0);

									//isCovering[coveredBy[i]] == i
									isCovered[isCovering[i]] = false;
									coveredBy[isCovering[i]] = isCovering[i];
									isCovered[i] = false;
									coveredBy[i] = i;
									Console::Instance().displayln(mobList[i].getName() + " has fallen.");

									if(i >= partySize)
									{
										isAlive[i] = true;
										Console::Instance().displayln(mobList[i].getName() + " has risen.");
										mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getMax());
									}
								}
							}
						}
					}

					//Acknowledge this mob is getting their turn
					++numTurns;
					mobReady = false;
					mobList[whoseTurn].getStat("turn").setCurrent(mobList[whoseTurn].getStat("turn").getCurrent() - 100);

					//Create the input sensors so our mob can make a decision
					int numInputs = BrainFactory::Instance().getBrain(mobList[whoseTurn].getFamilyDescriptor()).getNumInputs();
					double input[numInputs];
					for(int i = 0; i < numInputs; ++i)
						input[i] = 0;

					//Party position
					input[0] = 0;
					int i = 1;
					for(int j = 0; j < numMobs; ++j)
					{
						for(int k = 0; k < MasterStatMap::Instance().getNumContainers(); ++k)
						{
							//For every mob, place every container stat into the current mob's inputs
							//TODO kink mess with this shitpile till it works
							if(j < partySize)
								input[i] = mobList[j].getStat(MasterStatMap::Instance().getContainerStatDescriptor(k)).getCurrent();
							++i;
						}
					}

					pair<int, int> decisionPair = mobList[whoseTurn].chooseAction(input);
					int decision = decisionPair.first;
					int target = decisionPair.second;

					//forces the skellies to target this mob
					bool forceTarget = false;
					if(forceTarget && whoseTurn >= partySize)
						target = 1;

					bool randomTarget = true;
					if(randomTarget && whoseTurn >= partySize)
						target = (rand() % partySize);

					//Is the action hostile?
					bool hostile = (decision == 15) ||
									(decision == 17) ||
									(decision == 18) ||
									(decision == 19) ||
									(decision == 23) ||
									(decision == 27);

					if(hostile && isCovered[target] && mobList[coveredBy[target]].getStat("hp").getCurrent() <= 0)
					{
						isCovered[target] = false;
						coveredBy[target] = target;
					}

					//Disallow friendly fire or stray healing
					//If a party member
					if(whoseTurn < partySize)
					{
						if(hostile)
						{
							while(mobList[(target % enemySize) + partySize].getStat("hp").getCurrent() <= 0)
							{
								++target;
							}

							//Mod by # of foes for true target relative to foes
							target %= enemySize;
							//Add party size to find appropriate place in mobList
							target += partySize;

						}
						else
						{
							while(mobList[(target % partySize)].getStat("hp").getCurrent() <= 0)
							{
								++target;
							}

							//Mod by # of party members for true target
							target %= partySize;
						}
					}
					else  //Enemy
					{
						if(hostile)
						{
							while(mobList[(target % partySize)].getStat("hp").getCurrent() <= 0)
							{
								++target;
							}

							target %= partySize;
						}
						else
						{
							while(mobList[(target % enemySize) + partySize].getStat("hp").getCurrent() <= 0)
							{
								++target;
							}

							target %= enemySize;
							target += partySize;
						}
					}

					//If our target is sleeping, wake them and reset their turn counter
					if(isSlept[target] && (decision != 27))
					{
						isSlept[target] = false;
						mobList[target].getStat("turn").setCurrent(0);
					}

					int damage = 0;
					int healing = 0;

					if (decision == 15) //Mob hits
					{
						++numHits[whoseTurn];

						Console::Instance().displayln(mobList[whoseTurn].getName() + " attacks " + mobList[target].getName() + ".");

						if(isAlive[target])
						{
							//If our target is being covered by an ally who is awake
							if(isCovered[target] && !isSlept[coveredBy[target]])
							{
								Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
								target = coveredBy[target];
							}

							//base damage * (source str / target vit)
							damage = (10 + mobList[whoseTurn].getStat("lvl").getCurrent()) * ((double)mobList[whoseTurn].getStat("str").getCurrent() / (double)mobList[target].getStat("vit").getCurrent());

							if((rand() % 100) <= 10 + ((double)mobList[whoseTurn].getStat("dex").getCurrent() / (double)mobList[target].getStat("dex").getCurrent()))
							{
								damage *= 2;
								Console::Instance().displayln(mobList[whoseTurn].getName() + " scores a critical hit!");
							}

							if(isProtected[target])
								damage /= 2;

							if(isBerserked[whoseTurn])
								damage *= 2;
							if(isBerserked[target])
								damage *= 2;

							if(isBlinked[target])
							{
								damage = 0;
								isBlinked[target] = false;
								Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
							}
							else
							{
								mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);
								Console::Instance().display(mobList[target].getName() + " takes ");
								Console::Instance().displayInt(damage);
								Console::Instance().displayln(" points of damage.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
						}
					}
					else if (decision == 16) //Mob casts cure
					{
						++numCures[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Cure on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//cost + (wil - avg wil for lvl)
								healing = 2*(cost + mobList[whoseTurn].getStat("wil").getCurrent() - (2.5 * mobList[whoseTurn].getStat("lvl").getCurrent()));

								//Heal only to max, record amount healed for log
								if(mobList[target].getStat("hp").getCurrent() + healing > mobList[target].getStat("hp").getMax())
									healing = mobList[target].getStat("hp").getMax() - mobList[target].getStat("hp").getCurrent();

								mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() + healing);

								Console::Instance().display(mobList[target].getName() + " recovers ");
								Console::Instance().displayInt(healing);
								Console::Instance().displayln(" points of damage.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Cure on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 17) //Mob casts fire
					{
						++numFires[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Fire on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//If our target is being covered by an ally who is awake
								if(isCovered[target] && !isSlept[coveredBy[target]])
								{
									Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
									target = coveredBy[target];
								}

								if(isBlinked[target])
								{
									isBlinked[target] = false;
									Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
								}
								else
								{
									//2(cost + int - avg int for lvl)
									//TODO kink use elemental weaknesses to eventually turn this into the powerhouse it should be
									damage = 2 * (cost + mobList[whoseTurn].getStat("int").getCurrent() - (2.5 * mobList[whoseTurn].getStat("lvl").getCurrent()));

									if((rand() % 100) <= 10 + ((double)mobList[whoseTurn].getStat("int").getCurrent() / (double)mobList[target].getStat("wil").getCurrent()))
									{
										damage /= 2;
										Console::Instance().displayln(mobList[target].getName() + " resists!");
									}

									mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);
									Console::Instance().display(mobList[target].getName() + " takes ");
									Console::Instance().displayInt(damage);
									Console::Instance().displayln(" points of damage.");
								}
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Fire on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 18) //Mob casts poison
					{
						++numPoisons[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() * 0.05);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Poison on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//If our target is being covered by an ally who is awake
								if(isCovered[target] && !isSlept[coveredBy[target]])
								{
									Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
									target = coveredBy[target];
								}

								if(!isPoisoned[target])
								{
									if(isBlinked[target])
									{
										isBlinked[target] = false;
										Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
									}
									else
									{
										karma[whoseTurn] += 50;
										damage = 5 * ((double)mobList[whoseTurn].getStat("int").getCurrent() / (double)mobList[target].getStat("wil").getCurrent());

										mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);
										Console::Instance().display(mobList[target].getName() + " takes ");
										Console::Instance().displayInt(damage);
										Console::Instance().displayln(" points of damage.");

										isPoisoned[target] = true;
										Console::Instance().displayln(mobList[target].getName() + " is poisoned.");
									}
								}
								else
								{
									Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
								}
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Poison on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 19) //Mob uses reap
					{
						++numReaps[whoseTurn];

						Console::Instance().displayln(mobList[whoseTurn].getName() + " uses Reaper on " + mobList[target].getName() + ".");

						if(isAlive[target])
						{
							//If our target is being covered by an ally who is awake
							if(isCovered[target] && !isSlept[coveredBy[target]])
							{
								Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
								target = coveredBy[target];
							}

							damage = (mobList[whoseTurn].getStat("hp").getCurrent() / 10);
							mobList[whoseTurn].getStat("hp").setCurrent(mobList[whoseTurn].getStat("hp").getCurrent() - damage);
							Console::Instance().display(mobList[whoseTurn].getName() + " takes ");
							Console::Instance().displayInt(damage);
							Console::Instance().displayln(" points of damage.");
							//Special case to record damage received
							damageReceived[whoseTurn] += damage;

							//base damage * (source str / target vit)
							damage += (10 + mobList[whoseTurn].getStat("lvl").getCurrent()) * ((double)mobList[whoseTurn].getStat("str").getCurrent() / (double)mobList[target].getStat("vit").getCurrent());

							if((rand() % 100) <= 10 + ((double)mobList[whoseTurn].getStat("dex").getCurrent() / (double)mobList[target].getStat("dex").getCurrent()))
							{
								damage *= 2;
								Console::Instance().displayln(mobList[whoseTurn].getName() + " scores a critical hit!");
							}

							if(isProtected[target])
								damage /= 2;

							if(isBerserked[whoseTurn])
								damage *= 2;
							if(isBerserked[target])
								damage *= 2;

							if(isBlinked[target])
							{
								damage = 0;
								isBlinked[target] = false;
								Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
							}
							else
							{
								mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);
								Console::Instance().display(mobList[target].getName() + " takes ");
								Console::Instance().displayInt(damage);
								Console::Instance().displayln(" points of damage.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
						}
					}
					else if (decision == 21) //Mob casts regen
					{
						++numRegens[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Regen on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isRegened[target])
							{
								karma[whoseTurn] += 50;
								isRegened[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is regened.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Regen on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 22) //Mob casts refresh
					{
						++numRefresh[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 3);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Refresh on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isRefreshed[target])
							{
								karma[whoseTurn] += 200;
								isRefreshed[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is refreshed.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Refresh on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 23) //Mob casts drain
					{
						++numDrains[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Drain on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//If our target is being covered by an ally who is awake
								if(isCovered[target] && !isSlept[coveredBy[target]])
								{
									Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
									target = coveredBy[target];
								}

								if(isBlinked[target])
								{
									isBlinked[target] = false;
									Console::Instance().displayln(mobList[target].getName() + "'s shadow absorbs the damage.");
								}
								else
								{
									//2(cost + int - avg int for lvl)
									//TODO kink dark elemental?
									damage = cost + mobList[whoseTurn].getStat("int").getCurrent() - (2.5 * mobList[whoseTurn].getStat("lvl").getCurrent());

									if((rand() % 100) <= 10 + ((double)mobList[whoseTurn].getStat("int").getCurrent() / (double)mobList[target].getStat("wil").getCurrent()))
									{
										damage /= 2;
										Console::Instance().displayln(mobList[target].getName() + " resists!");
									}

									mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getCurrent() - damage);

									Console::Instance().display(mobList[target].getName() + " takes ");
									Console::Instance().displayInt(damage);
									Console::Instance().displayln(" points of damage.");


									//Heal only to max, record amount healed for log
									healing = damage;
									if(mobList[whoseTurn].getStat("hp").getCurrent() + healing > mobList[whoseTurn].getStat("hp").getMax())
										healing = mobList[whoseTurn].getStat("hp").getMax() - mobList[whoseTurn].getStat("hp").getCurrent();

									mobList[whoseTurn].getStat("hp").setCurrent(mobList[whoseTurn].getStat("hp").getCurrent() + healing);

									Console::Instance().display(mobList[whoseTurn].getName() + " recovers ");
									Console::Instance().displayInt(healing);
									Console::Instance().displayln(" points of damage.");

									//To prevent recording a whoopsie, or twice with damage
									healing = 0;
								}
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Drain on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 24) //Mob casts protect
					{
						++numProtects[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Protect on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isProtected[target])
							{
								karma[whoseTurn] += 100;
								isProtected[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is protected.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Protect on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 25) //Mob uses berserk
					{
						++numBerserks[whoseTurn];

						Console::Instance().displayln(mobList[whoseTurn].getName() + " uses Berserk.");

						if(!isBerserked[whoseTurn])
						{
							isBerserked[whoseTurn] = true;
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is berserked.");
						}
						else
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unaffected.");
					}
					else if (decision == 26) //Mob casts haste
					{
						++numHastes[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 4);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Haste on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isHasted[target])
							{
								karma[whoseTurn] += 150;
								isHasted[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is hasted.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Haste on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 27) //Mob casts sleep
					{
						++numSleeps[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Sleep on " + mobList[target].getName() + ".");

							if(isAlive[target])
							{
								//If our target is being covered by an ally who is awake
								if(isCovered[target] && !isSlept[coveredBy[target]])
								{
									Console::Instance().displayln(mobList[coveredBy[target]].getName() + " covers " + mobList[target].getName() + "!");
									target = coveredBy[target];
								}

								if(!isSlept[target])
								{
									karma[whoseTurn] += 25;
									isSlept[target] = true;
									Console::Instance().displayln(mobList[target].getName() + " is slept.");
								}
								else
								{
									Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
								}
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Sleep on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 28) //Mob casts blink
					{
						++numBlinks[whoseTurn];

						int cost = (mobList[whoseTurn].getStat("mp").getMax() / 10);
						if(mobList[whoseTurn].getStat("mp").getCurrent() >= cost)
						{
							mobList[whoseTurn].getStat("mp").setCurrent(mobList[whoseTurn].getStat("mp").getCurrent() - cost);

							Console::Instance().displayln(mobList[whoseTurn].getName() + " casts Blink on " + mobList[target].getName() + ".");

							if(isAlive[target] && !isBlinked[target])
							{
								karma[whoseTurn] += 25;
								isBlinked[target] = true;
								Console::Instance().displayln(mobList[target].getName() + " is blinked.");
							}
							else
							{
								Console::Instance().displayln(mobList[target].getName() + " is unaffected.");
							}
						}
						else
						{
							Console::Instance().displayln(mobList[whoseTurn].getName() + " is unable to cast Blink on " + mobList[target].getName() + ".");
						}
					}
					else if (decision == 29) //Mob uses cover
					{
						++numCovers[whoseTurn];

						Console::Instance().displayln(mobList[whoseTurn].getName() + " uses Cover on " + mobList[target].getName() + ".");

						if(whoseTurn==target)
							isCovered[whoseTurn] = false;
						else
							isCovered[target] = true;

						isCovering[whoseTurn] = target;
						coveredBy[target] = whoseTurn;
					}
					else //Mob idles
					{
						Console::Instance().displayln(mobList[whoseTurn].getName() + " idles.");
						++numIdles[whoseTurn];
					}

					//Record damage, healing, and check for whoopsies
					damageReceived[target] += damage;
					damageDealt[whoseTurn] += damage;
					healingDealt[whoseTurn] += healing;

					if((whoseTurn < partySize && target < partySize)||(whoseTurn >= partySize && target >= partySize))
						whoopsieDealt[whoseTurn] += damage;
					if((whoseTurn < partySize && target >= partySize)||(whoseTurn >= partySize && target < partySize))
						whoopsieDealt[whoseTurn] += healing;

					//Check for target's death
					if(mobList[target].getStat("hp").getCurrent() <= 0 && isAlive[target])
					{
						isAlive[target] = false;
						++numDeaths[target];
//						mobList[target].setStat("turn", 0);

						isCovered[isCovering[target]] = false;
						coveredBy[isCovering[target]] = isCovering[target];
						isCovered[target] = false;
						coveredBy[target] = target;

						Console::Instance().displayln(mobList[target].getName() + " has fallen.");

						if(target >= partySize)
						{
							isAlive[target] = true;
							Console::Instance().displayln(mobList[target].getName() + " has risen.");
							mobList[target].getStat("hp").setCurrent(mobList[target].getStat("hp").getMax());
						}
					}
				}

				for(int i = 0; i < partySize; ++i)
				{
					partyDeaths += numDeaths[i];
				}

				for(int i = 0; i < enemySize; ++i)
				{
					skeletonDeaths += numDeaths[i + partySize];
				}

				//paladin
				//dark knight
				//magician
				//cleric
				//sorcerer

				int fitness[10];
				fitness[0] = numTurns + skeletonDeaths + karma[0] + ((double)(damageDealt[0] + healingDealt[0])/numTurns);
				fitness[1] = numTurns + skeletonDeaths + karma[1] + ((double)(damageDealt[1] + healingDealt[1])/numTurns);
				fitness[2] = numTurns + skeletonDeaths + karma[2] + ((double)(damageDealt[2] + healingDealt[2])/numTurns);
				fitness[3] = damageDealt[2] + healingDealt[2];
//				fitness[0] = /*(skeletonDeaths * 100) + */damageDealt[0] + healingDealt[0] - whoopsieDealt[0];
//				fitness[1] = /*(skeletonDeaths * 100) + */damageDealt[1] + healingDealt[1] - whoopsieDealt[1];
//				fitness[2] = /*(skeletonDeaths * 100) + */damageDealt[2] + healingDealt[2] - whoopsieDealt[2];
//				fitness[3] = /*(skeletonDeaths * 100) + */damageDealt[3] + healingDealt[3] - whoopsieDealt[3];
//				fitness[4] = /*(skeletonDeaths * 100) + */damageDealt[4] + healingDealt[4] - whoopsieDealt[4];
//				fitness[0] = (skeletonDeaths * 100) + damageDealt[0] + healingDealt[0] - whoopsieDealt[0];
//				fitness[1] = (skeletonDeaths * 100) + damageDealt[1] + healingDealt[1] - whoopsieDealt[1];
//				fitness[2] = (skeletonDeaths * 100) + damageDealt[2] + healingDealt[2] - whoopsieDealt[2];
//				fitness[3] = (skeletonDeaths * 100) + damageDealt[3] + healingDealt[3] - whoopsieDealt[3];
//				fitness[4] = (skeletonDeaths * 100) + damageDealt[4] + healingDealt[4] - whoopsieDealt[4];
//				fitness[5] = damageDealt[5] - whoopsieDealt[5];
//				fitness[6] = damageDealt[6] - whoopsieDealt[6];
//				fitness[7] = damageDealt[7] - whoopsieDealt[7];
//				fitness[8] = damageDealt[8] - whoopsieDealt[8];
//				fitness[9] = damageDealt[9] - whoopsieDealt[9];

				for(int i = 0; i < numMobs; ++i)
				{
					if(fitness[i] < 0)
						fitness[i] = 0;

					mobList[i].retireOrganism(fitness[i]);
				}

				Console::Instance().display("------------- Encounter ");
				Console::Instance().displayInt(numEncounters);
				Console::Instance().display("-------------");
				Console::Instance().newLine();

				++numEncounters;

				Console::Instance().display("Turns survived: ");
				Console::Instance().displayInt(numTurns);
				Console::Instance().newLine();

				Console::Instance().display("Party Deaths: ");
				Console::Instance().displayInt(partyDeaths);
				Console::Instance().newLine();

				Console::Instance().display("Skeleton Deaths: ");
				Console::Instance().displayInt(skeletonDeaths);
				Console::Instance().newLine();

				for(int i = 0; i < numMobs; ++i)
				{
					Console::Instance().displayln("------");
					Console::Instance().displayln(mobList[i].getName());
					Console::Instance().displayln("------");
					Console::Instance().display("Fitness: ");
					Console::Instance().displayInt(fitness[i]);
					Console::Instance().newLine();
					Console::Instance().display("Hits: ");
					Console::Instance().displayInt(numHits[i]);
					Console::Instance().newLine();
					Console::Instance().display("Cures: ");
					Console::Instance().displayInt(numCures[i]);
					Console::Instance().newLine();
					Console::Instance().display("Covers: ");
					Console::Instance().displayInt(numCovers[i]);
					Console::Instance().newLine();
					Console::Instance().display("Reaps: ");
					Console::Instance().displayInt(numReaps[i]);
					Console::Instance().newLine();
					Console::Instance().display("Berserks: ");
					Console::Instance().displayInt(numBerserks[i]);
					Console::Instance().newLine();
					Console::Instance().display("Drains: ");
					Console::Instance().displayInt(numDrains[i]);
					Console::Instance().newLine();
					Console::Instance().display("Fires: ");
					Console::Instance().displayInt(numFires[i]);
					Console::Instance().newLine();
					Console::Instance().display("Poisons: ");
					Console::Instance().displayInt(numPoisons[i]);
					Console::Instance().newLine();
					Console::Instance().display("Sleeps: ");
					Console::Instance().displayInt(numSleeps[i]);
					Console::Instance().newLine();
					Console::Instance().display("Regens: ");
					Console::Instance().displayInt(numRegens[i]);
					Console::Instance().newLine();
					Console::Instance().display("Protects: ");
					Console::Instance().displayInt(numProtects[i]);
					Console::Instance().newLine();
					Console::Instance().display("Refresh: ");
					Console::Instance().displayInt(numRefresh[i]);
					Console::Instance().newLine();
					Console::Instance().display("Hastes: ");
					Console::Instance().displayInt(numHastes[i]);
					Console::Instance().newLine();
					Console::Instance().display("Blinks: ");
					Console::Instance().displayInt(numBlinks[i]);
					Console::Instance().newLine();
					Console::Instance().display("Deaths: ");
					Console::Instance().displayInt(numDeaths[i]);
					Console::Instance().newLine();
					Console::Instance().display("Damage Dealt: ");
					Console::Instance().displayInt(damageDealt[i]);
					Console::Instance().newLine();
					Console::Instance().display("Healing Dealt: ");
					Console::Instance().displayInt(healingDealt[i]);
					Console::Instance().newLine();
					Console::Instance().display("Whoopsies: ");
					Console::Instance().displayInt(whoopsieDealt[i]);
					Console::Instance().newLine();
					Console::Instance().display("Damage Received: ");
					Console::Instance().displayInt(damageReceived[i]);
					Console::Instance().newLine();
					Console::Instance().display("Sleep: ");
					Console::Instance().displayBool(isSlept[i]);
					Console::Instance().newLine();
					Console::Instance().display("Poisoned: ");
					Console::Instance().displayBool(isPoisoned[i]);
					Console::Instance().newLine();
					Console::Instance().display("Regen: ");
					Console::Instance().displayBool(isRegened[i]);
					Console::Instance().newLine();
					Console::Instance().display("Protect: ");
					Console::Instance().displayBool(isProtected[i]);
					Console::Instance().newLine();
					Console::Instance().display("Refreshed: ");
					Console::Instance().displayBool(isRefreshed[i]);
					Console::Instance().newLine();
					Console::Instance().display("Haste: ");
					Console::Instance().displayBool(isHasted[i]);
					Console::Instance().newLine();
					Console::Instance().display("Alive: ");
					Console::Instance().displayBool(isAlive[i]);
					Console::Instance().newLine();

					mobList[i].getStat("hp").setCurrent(mobList[i].getStat("hp").getMax());
					mobList[i].getStat("mp").setCurrent(mobList[i].getStat("mp").getMax());
					mobList[i].getStat("turn").setCurrent(0);
				}
			}

			return "";
		}
};

#endif
