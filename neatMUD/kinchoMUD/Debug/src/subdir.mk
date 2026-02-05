################################################################################
# Automatically-generated file. Do not edit!
################################################################################

# Add inputs and outputs from these tool invocations to the build variables 
CPP_SRCS += \
../src/Action.cpp \
../src/Area.cpp \
../src/Battle.cpp \
../src/BrainFactory.cpp \
../src/Chain.cpp \
../src/Console.cpp \
../src/Direction.cpp \
../src/Door.cpp \
../src/Exit.cpp \
../src/Login.cpp \
../src/MasterStatMap.cpp \
../src/Mob.cpp \
../src/MobBrain.cpp \
../src/Player.cpp \
../src/Room.cpp \
../src/Stat.cpp \
../src/spoc2.cpp 

OBJS += \
./src/Action.o \
./src/Area.o \
./src/Battle.o \
./src/BrainFactory.o \
./src/Chain.o \
./src/Console.o \
./src/Direction.o \
./src/Door.o \
./src/Exit.o \
./src/Login.o \
./src/MasterStatMap.o \
./src/Mob.o \
./src/MobBrain.o \
./src/Player.o \
./src/Room.o \
./src/Stat.o \
./src/spoc2.o 

CPP_DEPS += \
./src/Action.d \
./src/Area.d \
./src/Battle.d \
./src/BrainFactory.d \
./src/Chain.d \
./src/Console.d \
./src/Direction.d \
./src/Door.d \
./src/Exit.d \
./src/Login.d \
./src/MasterStatMap.d \
./src/Mob.d \
./src/MobBrain.d \
./src/Player.d \
./src/Room.d \
./src/Stat.d \
./src/spoc2.d 


# Each subdirectory must supply rules for building sources it contributes
src/%.o: ../src/%.cpp
	@echo 'Building file: $<'
	@echo 'Invoking: GCC C++ Compiler'
	g++ -I"/mnt/hgfs/G/home/dev/kincho/rtNEAT" -O0 -g3 -Wall -c -fmessage-length=0 -MMD -MP -MF"$(@:%.o=%.d)" -MT"$(@:%.o=%.d)" -o "$@" "$<"
	@echo 'Finished building: $<'
	@echo ' '


