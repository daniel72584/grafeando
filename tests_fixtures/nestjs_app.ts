import { Controller, Get, Injectable } from '@nestjs/common';

@Injectable()
export class UserService {
  getUser(id: string) {
    return { id, name: 'Alice' };
  }
}

@Controller('users')
export class UserController {
  constructor(private readonly userService: UserService) {}

  @Get()
  findAll() {
    return this.userService.getUser('1');
  }
}
