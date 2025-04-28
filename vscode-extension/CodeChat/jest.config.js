module.exports = {
    preset: 'ts-jest',
    testEnvironment: 'node',
    globals: {
        'ts-jest': {
          tsconfig: 'tsconfig.jest.json'
        }
      },
    roots: ['<rootDir>/src'],
    moduleFileExtensions: ['ts','js','json'],
    transform: { '^.+\\.ts$': 'ts-jest' }
  };
  