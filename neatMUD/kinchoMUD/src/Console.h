/*
 * Console.h
 *
 *  Created on: Dec 16, 2010
 *      Author: kincho
 */

#ifndef CONSOLE_H_
#define CONSOLE_H_

#include <cstdlib>
#include <string>
#include <iostream>
#include <map>

using namespace std;

class Console
{
	private:
		bool active;

		Console(); // Private constructor

		Console(const Console&); // Prevent copy-construction

		Console& operator=(const Console&); // Prevent assignment

	public:
		static Console& Instance();

		static void clear_screen();

		static void display(string out);

		static void newLine();

		static void displayln(string out);

		static void displayInt(int out);

		static void displayBool(bool out);

		static string prompt(map<string, int> vals);

		static string prompt();

		bool isActive();

		void start();

		void quit();
};

#endif /* CONSOLE_H_ */
