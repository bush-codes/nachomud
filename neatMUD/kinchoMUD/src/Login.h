/*
 * Login.h
 *
 *  Created on: Dec 16, 2010
 *      Author: kincho
 */

#ifndef LOGIN_H_
#define LOGIN_H_

#include <string>

#include "rapidxml-1.13/rapidxml.hpp"
#include "rapidxml-1.13/rapidxml_utils.hpp"

using namespace std;
using namespace rapidxml;

class Login
{
	private:
		int md; //xml main page descriptor
		string description;
		bool valid;

	public:
		Login();

		Login(const char *filename);

		virtual ~Login();

		const int getDescriptor() const;

		const string getDescription();
};
#endif /* LOGIN_H_ */
